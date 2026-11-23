// Horizon / Switch 2 audio output service (audout:u and aud:u cmd 1 IAudioOutManager / IAudioOut)
// backed by SDL3 audio stream playback and real-time buffer release pacing.
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <SDL3/SDL.h>

#include "audren.h"
#include "cfg.h"
#include "host.h"
#include "ipc.h"
#include "platform/platform.h"

#define AUDOUT_MAX_QUEUED 32u
#define AUDOUT_MAX_RELEASED 64u

typedef struct {
    uint64_t tag;
    uint64_t data_addr;
    uint64_t data_size;
} AudoutBuf;

typedef struct {
    PlatMutex lock;
    PlatThread *thread;
    volatile int32_t alive;
    uint32_t sample_rate, channels, format;
    volatile uint32_t state;   // 0 = Started, 1 = Stopped
    float volume;
    uint32_t event;
    uint64_t played_samples;
    AudoutBuf queued[AUDOUT_MAX_QUEUED];
    uint32_t q_head, q_count;
    uint64_t released[AUDOUT_MAX_RELEASED];
    uint32_t r_head, r_count;
    SDL_AudioStream *stream;
} AudioOut;

static IpcBuffer pick_buf(const IpcBuffer *a, unsigned na, const IpcBuffer *b, unsigned nb, unsigned i) {
    IpcBuffer x = i < na ? a[i] : (IpcBuffer){0}, y = i < nb ? b[i] : (IpcBuffer){0};
    return x.size ? x : y;
}

static void mark_auto_out(const IpcRequest *rq, IpcResponse *rs) {
    for (unsigned i = 0; i < rq->nc && rs->nxout < IPC_MAX_BUF; i++) {
        if (rq->c[i].size && (i >= rq->nb || !rq->b[i].size))
            rs->xout[rs->nxout++] = (IpcBuffer){rq->c[i].addr, rq->c[i].size, i};
    }
}

static void push_released_locked(AudioOut *o, uint64_t tag) {
    if (o->r_count >= AUDOUT_MAX_RELEASED) {
        o->r_head = (o->r_head + 1) % AUDOUT_MAX_RELEASED;
        o->r_count--;
    }
    o->released[(o->r_head + o->r_count) % AUDOUT_MAX_RELEASED] = tag;
    o->r_count++;
}

static int drain_queued_to_released_locked(AudioOut *o) {
    int moved = 0;
    while (o->q_count > 0) {
        AudoutBuf b = o->queued[o->q_head];
        o->q_head = (o->q_head + 1) % AUDOUT_MAX_QUEUED;
        o->q_count--;
        push_released_locked(o, b.tag);
        moved++;
    }
    return moved;
}

static void open_sdl_stream(AudioOut *o) {
    const char *mode = cfg_get("TOTK_AUDIO");
    if ((mode && !strcmp(mode, "none")) || cfg_get("TOTK_AUDIO_OFF")) {
        rt_log("audout: TOTK_AUDIO=none: running without audio device");
        return;
    }
    if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {
        rt_log("audout: SDL audio init failed (%s): running silently", SDL_GetError());
        return;
    }
    SDL_AudioSpec spec = {SDL_AUDIO_S16, (int)o->channels, (int)o->sample_rate};
    o->stream = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, NULL, NULL);
    if (!o->stream) {
        rt_log("audout: no output device (%s): running silently", SDL_GetError());
        return;
    }
    SDL_SetAudioStreamGain(o->stream, o->volume);
}

static void audout_thread(void *arg) {
    AudioOut *o = arg;
    while (__atomic_load_n(&o->alive, __ATOMIC_ACQUIRE)) {
        AudoutBuf b = {0};
        int have = 0;
        uint32_t rate = 48000, ch = 2;
        SDL_AudioStream *stream = NULL;

        plat_mutex_lock(&o->lock);
        if (__atomic_load_n(&o->state, __ATOMIC_ACQUIRE) == 0 && o->q_count > 0) {
            b = o->queued[o->q_head];
            o->q_head = (o->q_head + 1) % AUDOUT_MAX_QUEUED;
            o->q_count--;
            rate = o->sample_rate;
            ch = o->channels;
            stream = o->stream;
            have = 1;
        }
        plat_mutex_unlock(&o->lock);

        if (!have) {
            plat_sleep_ms(2);
            continue;
        }

        if (stream && b.data_size > 0 && b.data_size <= (16ull << 20) &&
            plat_mem_readable((uintptr_t)b.data_addr, (size_t)b.data_size)) {
            SDL_PutAudioStreamData(stream, (const void *)(uintptr_t)b.data_addr, (int)b.data_size);
        }

        uint64_t bpf = (uint64_t)ch * 2u;
        uint64_t frames = bpf ? b.data_size / bpf : 0;
        if (stream) {
            uint64_t limit = b.data_size * 2u;
            while (__atomic_load_n(&o->alive, __ATOMIC_ACQUIRE) &&
                   __atomic_load_n(&o->state, __ATOMIC_ACQUIRE) == 0 &&
                   (uint64_t)SDL_GetAudioStreamQueued(stream) > limit) {
                plat_sleep_ms(2);
            }
        } else {
            uint64_t dur_ms = (frames && rate) ? (frames * 1000ull + rate - 1) / rate : 1;
            if (dur_ms > 200) dur_ms = 200;
            for (uint64_t elapsed = 0;
                 elapsed < dur_ms &&
                 __atomic_load_n(&o->alive, __ATOMIC_ACQUIRE) &&
                 __atomic_load_n(&o->state, __ATOMIC_ACQUIRE) == 0;
                 elapsed += 5) {
                uint64_t step = dur_ms - elapsed;
                plat_sleep_ms((uint32_t)(step > 5 ? 5 : step));
            }
        }

        plat_mutex_lock(&o->lock);
        o->played_samples += frames;
        push_released_locked(o, b.tag);
        plat_mutex_unlock(&o->lock);
        kern_event_signal(o->event);
    }
}

static void audout_close(void *arg) {
    AudioOut *o = arg;
    if (!o) return;
    plat_xchg32(&o->alive, 0);
    int away = kern_core_away();
    if (o->thread) plat_thread_join(o->thread);
    kern_core_back(&away);
    if (o->stream) SDL_DestroyAudioStream(o->stream);
    if (o->event) kern_handle_close(o->event);
    free(o);
}

static void audout_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    AudioOut *o = s->state;
    switch (rq->cmd) {
    case 0: {   // GetAudioOutState
        uint32_t st = __atomic_load_n(&o->state, __ATOMIC_ACQUIRE);
        IPC_OUT(rs, st);
        return;
    }
    case 1:   // StartAudioOut
        plat_mutex_lock(&o->lock);
        __atomic_store_n(&o->state, 0u, __ATOMIC_RELEASE);
        if (o->stream) SDL_ResumeAudioStreamDevice(o->stream);
        plat_mutex_unlock(&o->lock);
        return;
    case 2: {   // StopAudioOut
        int moved;
        plat_mutex_lock(&o->lock);
        __atomic_store_n(&o->state, 1u, __ATOMIC_RELEASE);
        if (o->stream) {
            SDL_PauseAudioStreamDevice(o->stream);
            SDL_ClearAudioStream(o->stream);
        }
        moved = drain_queued_to_released_locked(o);
        plat_mutex_unlock(&o->lock);
        if (moved) kern_event_signal(o->event);
        return;
    }
    case 3: case 7: {   // AppendAudioOutBuffer / AppendAudioOutBufferAuto
        uint64_t tag = IPC_ARG(rq, uint64_t, 0);
        IpcBuffer in = pick_buf(rq->a, rq->na, rq->x, rq->nx, 0);
        if (in.size < 40) { rs->result = 0x299u; return; }
        const uint64_t *d = ipc_guest(in.addr, 40);
        uint64_t data_addr = d[1] + d[4];
        uint64_t data_size = d[3];
        if (data_addr < d[1]) { rs->result = 0x299u; return; }
        plat_mutex_lock(&o->lock);
        if (o->q_count >= AUDOUT_MAX_QUEUED) {
            plat_mutex_unlock(&o->lock);
            rs->result = 0x299u;
            return;
        }
        o->queued[(o->q_head + o->q_count) % AUDOUT_MAX_QUEUED] = (AudoutBuf){tag, data_addr, data_size};
        o->q_count++;
        plat_mutex_unlock(&o->lock);
        return;
    }
    case 4:   // RegisterBufferEvent
        rs->copy[rs->ncopy++] = kern_event_readable(o->event);
        return;
    case 5: case 8: {   // GetReleasedAudioOutBuffers / GetReleasedAudioOutBuffersAuto
        IpcBuffer out = pick_buf(rq->b, rq->nb, rq->c, rq->nc, 0);
        uint64_t *dst = out.size >= 8 ? ipc_guest(out.addr, out.size) : NULL;
        uint32_t max_tags = dst ? (uint32_t)(out.size / 8) : 0;
        uint32_t count = 0;
        plat_mutex_lock(&o->lock);
        while (count < max_tags && o->r_count > 0) {
            dst[count++] = o->released[o->r_head];
            o->r_head = (o->r_head + 1) % AUDOUT_MAX_RELEASED;
            o->r_count--;
        }
        plat_mutex_unlock(&o->lock);
        if (rq->cmd == 8) mark_auto_out(rq, rs);
        IPC_OUT(rs, count);
        return;
    }
    case 6: {   // ContainsAudioOutBuffer
        uint64_t tag = IPC_ARG(rq, uint64_t, 0);
        uint8_t found = 0;
        plat_mutex_lock(&o->lock);
        for (uint32_t i = 0; i < o->q_count; i++) {
            if (o->queued[(o->q_head + i) % AUDOUT_MAX_QUEUED].tag == tag) {
                found = 1;
                break;
            }
        }
        plat_mutex_unlock(&o->lock);
        IPC_OUT(rs, found);
        return;
    }
    case 9: {   // GetAudioOutBufferCount
        plat_mutex_lock(&o->lock);
        uint32_t cnt = o->q_count;
        plat_mutex_unlock(&o->lock);
        IPC_OUT(rs, cnt);
        return;
    }
    case 10: {   // GetAudioOutPlayedSampleCount
        plat_mutex_lock(&o->lock);
        uint64_t played = o->played_samples;
        plat_mutex_unlock(&o->lock);
        IPC_OUT(rs, played);
        return;
    }
    case 11: {   // FlushAudioOutBuffers
        int moved;
        plat_mutex_lock(&o->lock);
        if (o->stream) SDL_ClearAudioStream(o->stream);
        moved = drain_queued_to_released_locked(o);
        plat_mutex_unlock(&o->lock);
        if (moved) kern_event_signal(o->event);
        uint8_t flushed = moved > 0 ? 1 : 0;
        IPC_OUT(rs, flushed);
        return;
    }
    case 12: {   // SetAudioOutVolume
        float vol = IPC_ARG(rq, float, 0);
        plat_mutex_lock(&o->lock);
        o->volume = vol;
        if (o->stream) SDL_SetAudioStreamGain(o->stream, vol);
        plat_mutex_unlock(&o->lock);
        return;
    }
    case 13: {   // GetAudioOutVolume
        plat_mutex_lock(&o->lock);
        float vol = o->volume;
        plat_mutex_unlock(&o->lock);
        IPC_OUT(rs, vol);
        return;
    }
    default:
        ipc_unimplemented(s, rq);
    }
}

void audout_manager_handler(IpcSession *s, const IpcRequest *rq, IpcResponse *rs) {
    static const char dev_name[] = "DeviceOut";
    switch (rq->cmd) {
    case 0: case 2: {   // ListAudioOuts / ListAudioOutsAuto
        IpcBuffer out = pick_buf(rq->b, rq->nb, rq->c, rq->nc, 0);
        if (out.size > 0) {
            uint64_t n = out.size < 0x100 ? out.size : 0x100;
            uint8_t *dst = ipc_guest(out.addr, n);
            memset(dst, 0, (size_t)n);
            size_t cp = sizeof(dev_name) < (size_t)n ? sizeof(dev_name) : (size_t)n;
            memcpy(dst, dev_name, cp);
            dst[cp - 1] = '\0';
        }
        if (rq->cmd == 2) mark_auto_out(rq, rs);
        uint32_t count = 1;
        IPC_OUT(rs, count);
        return;
    }
    case 1: case 3: {   // OpenAudioOut / OpenAudioOutAuto
        uint32_t rate = rq->data_size >= 4 ? IPC_ARG(rq, uint32_t, 0) : 0;
        uint16_t ch = rq->data_size >= 6 ? IPC_ARG(rq, uint16_t, 4) : 0;
        rate = rate ? rate : 48000;
        ch = (ch >= 1 && ch <= 6) ? ch : 2;

        IpcBuffer out = pick_buf(rq->b, rq->nb, rq->c, rq->nc, 0);
        if (out.size > 0) {
            uint64_t n = out.size < 0x100 ? out.size : 0x100;
            uint8_t *dst = ipc_guest(out.addr, n);
            memset(dst, 0, (size_t)n);
            size_t cp = sizeof(dev_name) < (size_t)n ? sizeof(dev_name) : (size_t)n;
            memcpy(dst, dev_name, cp);
            dst[cp - 1] = '\0';
        }
        if (rq->cmd == 3) mark_auto_out(rq, rs);

        AudioOut *o = calloc(1, sizeof *o);
        if (!o) rt_fatal("audout: out of memory");
        o->lock = (PlatMutex)PLAT_MUTEX_INIT;
        o->alive = 1;
        o->sample_rate = rate;
        o->channels = ch;
        o->format = 2;
        o->state = 1;
        o->volume = 1.0f;
        o->event = kern_event_new();
        open_sdl_stream(o);
        o->thread = plat_thread_new(audout_thread, o, "audout");
        if (!o->thread) rt_fatal("audout: cannot start playback thread");

        rt_log("audout: opened 'DeviceOut' %u Hz %u ch PCM16", o->sample_rate, o->channels);
        struct { uint32_t rate, ch, fmt, state; } out_p = {o->sample_rate, o->channels, 2u, 1u};
        IPC_OUT(rs, out_p);
        rs->move[rs->nmove++] = ipc_session_new("IAudioOut", audout_handler, o, audout_close);
        return;
    }
    default:
        ipc_unimplemented(s, rq);
    }
}
