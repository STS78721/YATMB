// H.264 through Media Foundation's software decoder (the synchronous H.264 MFT that ships with Windows; an "N" edition
// without the Media Feature Pack has none, and then h264_open fails and the game's movie stays black).
// Packets go in as Annex B: a length-prefixed packet (MP4 samples) has its lengths turned into start codes, and the
// SPS / PPS from the configuration go in front of the first packet after opening or a flush. The decoder reorders B
// frames itself; its pictures come out in display order with the times they went in with.
#define COBJMACROS
#include <windows.h>
#include <mfapi.h>
#include <mferror.h>
#include <mfidl.h>
#include <mftransform.h>
#include <stdlib.h>
#include <string.h>

#include "h264.h"
#include "host.h"

struct H264Dec {
    IMFTransform *t;
    unsigned w, h;              // the stream's size: pictures are cropped to it
    UINT32 fw, fh, stride;      // the decoder's NV12 frame (height aligned to 16) and its row pitch
    uint8_t *header;            // SPS / PPS as Annex B, put in front of the next packet after open / flush
    size_t header_size;
    int need_header, nal_len;   // nal_len: length size of length-prefixed packets
    uint8_t *scratch;
    size_t scratch_cap;
    unsigned failures;
    int64_t last_pts;           // the last picture's time: a picture before it came out of display order
    int have_last;
};


static INIT_ONCE mf_once = INIT_ONCE_STATIC_INIT;
static int mf_ok;
static BOOL CALLBACK mf_start(PINIT_ONCE o, PVOID p, PVOID *x) {
    (void)o, (void)p, (void)x;
    mf_ok = SUCCEEDED(MFStartup(MF_VERSION, MFSTARTUP_NOSOCKET));
    return TRUE;
}
// Media Foundation runs in the multithreaded apartment; each guest thread that calls in joins it once (a thread
// already in a single-threaded apartment stays there, and the MFT, which allows both, still works).
static void com_join(void) {
    static __thread int joined;
    if (!joined) joined = 1, CoInitializeEx(NULL, COINIT_MULTITHREADED);
}

const char *h264_backend(void) { return "Media Foundation"; }

static void put_nal(uint8_t **o, size_t *n, size_t *cap, const uint8_t *p, size_t len) {
    if (*n + len + 4 > *cap) {
        *cap = (*n + len + 4) * 2;
        if (!(*o = realloc(*o, *cap))) rt_fatal("h264: out of memory");
    }
    static const uint8_t sc[4] = {0, 0, 0, 1};
    memcpy(*o + *n, sc, 4), memcpy(*o + *n + 4, p, len);
    *n += len + 4;
}

// avcC (ISO 14496-15): 1, profile, compat, level, 0xfc | length size - 1, 0xe0 | SPS count, (u16 size, SPS)*, PPS
// count, (u16 size, PPS)*. Anything else is taken as Annex B already.
static void read_config(H264Dec *d, const uint8_t *p, size_t n) {
    d->nal_len = 4;
    if (!p || !n) return;
    if (n >= 7 && p[0] == 1) {
        d->nal_len = (p[4] & 3) + 1;
        size_t at = 5, cap = 0;
        for (int set = 0; set < 2 && at < n; set++) {
            unsigned count = set ? p[at] : p[at] & 31;
            at++;
            for (unsigned k = 0; k < count && at + 2 <= n; k++) {
                size_t len = (size_t)p[at] << 8 | p[at + 1];
                at += 2;
                if (at + len > n) break;
                put_nal(&d->header, &d->header_size, &cap, p + at, len);
                at += len;
            }
        }
    } else {
        if (!(d->header = malloc(n))) rt_fatal("h264: out of memory");
        memcpy(d->header, p, n), d->header_size = n;
    }
}

static int annexb(const uint8_t *p, size_t n) {
    return n >= 4 && p[0] == 0 && p[1] == 0 && (p[2] == 1 || (p[2] == 0 && p[3] == 1));
}

// The packet as Annex B in d->scratch (with the header in front when one is owed).
static size_t prepare(H264Dec *d, const uint8_t *p, size_t n) {
    size_t out = 0;
    if (d->need_header && d->header_size) {
        if (d->header_size > d->scratch_cap && !(d->scratch = realloc(d->scratch, d->scratch_cap = d->header_size * 2)))
            rt_fatal("h264: out of memory");
        memcpy(d->scratch, d->header, d->header_size), out = d->header_size;
    }
    d->need_header = 0;
    if (annexb(p, n)) {
        if (out + n > d->scratch_cap && !(d->scratch = realloc(d->scratch, d->scratch_cap = (out + n) * 2)))
            rt_fatal("h264: out of memory");
        memcpy(d->scratch + out, p, n);
        return out + n;
    }
    for (size_t at = 0; at + (size_t)d->nal_len <= n;) {
        size_t len = 0;
        for (int k = 0; k < d->nal_len; k++) len = len << 8 | p[at + k];
        at += (size_t)d->nal_len;
        if (len > n - at) len = n - at;
        put_nal(&d->scratch, &out, &d->scratch_cap, p + at, len);
        at += len;
    }
    return out;
}

static HRESULT set_nv12_output(H264Dec *d) {
    IMFMediaType *mt;
    for (DWORD i = 0; SUCCEEDED(IMFTransform_GetOutputAvailableType(d->t, 0, i, &mt)); i++) {
        GUID sub;
        HRESULT hr = IMFMediaType_GetGUID(mt, &MF_MT_SUBTYPE, &sub);
        if (SUCCEEDED(hr) && IsEqualGUID(&sub, &MFVideoFormat_NV12)) {
            hr = IMFTransform_SetOutputType(d->t, 0, mt, 0);
            UINT64 size = 0;
            if (SUCCEEDED(hr) && SUCCEEDED(IMFMediaType_GetUINT64(mt, &MF_MT_FRAME_SIZE, &size)))
                d->fw = (UINT32)(size >> 32), d->fh = (UINT32)size;
            UINT32 stride = 0;
            d->stride = SUCCEEDED(IMFMediaType_GetUINT32(mt, &MF_MT_DEFAULT_STRIDE, &stride)) && (INT32)stride > 0
                            ? stride : d->fw;
            IMFMediaType_Release(mt);
            return hr;
        }
        IMFMediaType_Release(mt);
    }
    return MF_E_INVALIDMEDIATYPE;
}

static IMFTransform *find_decoder(void) {
    MFT_REGISTER_TYPE_INFO in = {MFMediaType_Video, MFVideoFormat_H264};
    IMFActivate **act = NULL;
    UINT32 n = 0;
    IMFTransform *t = NULL;
    if (FAILED(MFTEnumEx(MFT_CATEGORY_VIDEO_DECODER, MFT_ENUM_FLAG_SYNCMFT | MFT_ENUM_FLAG_LOCALMFT |
                         MFT_ENUM_FLAG_SORTANDFILTER, &in, NULL, &act, &n)))
        return NULL;
    for (UINT32 i = 0; i < n; i++) {
        if (!t) IMFActivate_ActivateObject(act[i], &IID_IMFTransform, (void **)&t);
        IMFActivate_Release(act[i]);
    }
    CoTaskMemFree(act);
    return t;
}

H264Dec *h264_open(unsigned w, unsigned h, const uint8_t *config, size_t config_size) {
    com_join();
    InitOnceExecuteOnce(&mf_once, mf_start, NULL, NULL);
    if (!mf_ok) return rt_log("h264: Media Foundation did not start"), NULL;
    IMFTransform *t = find_decoder();
    if (!t) return rt_log("h264: no H.264 decoder in Media Foundation (Windows N without the Media Feature Pack?)"), NULL;
    H264Dec *d = calloc(1, sizeof *d);
    if (!d) rt_fatal("h264: out of memory");
    d->t = t, d->w = w, d->h = h, d->fw = w, d->fh = h, d->stride = w, d->need_header = 1;
    read_config(d, config, config_size);
    IMFMediaType *mt = NULL;
    HRESULT hr = MFCreateMediaType(&mt);
    if (SUCCEEDED(hr)) {
        IMFMediaType_SetGUID(mt, &MF_MT_MAJOR_TYPE, &MFMediaType_Video);
        IMFMediaType_SetGUID(mt, &MF_MT_SUBTYPE, &MFVideoFormat_H264);
        IMFMediaType_SetUINT64(mt, &MF_MT_FRAME_SIZE, (UINT64)w << 32 | h);
        IMFMediaType_SetUINT32(mt, &MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive);
        hr = IMFTransform_SetInputType(t, 0, mt, 0);
        IMFMediaType_Release(mt);
    }
    if (SUCCEEDED(hr)) hr = set_nv12_output(d);
    if (SUCCEEDED(hr)) {
        IMFTransform_ProcessMessage(t, MFT_MESSAGE_NOTIFY_BEGIN_STREAMING, 0);
        IMFTransform_ProcessMessage(t, MFT_MESSAGE_NOTIFY_START_OF_STREAM, 0);
    }
    if (FAILED(hr)) {
        rt_log("h264: the Media Foundation decoder refused %ux%u (%#lx)", w, h, (unsigned long)hr);
        h264_close(d);
        return NULL;
    }
    return d;
}

// The picture of an output sample, cropped to the stream's size.
static int take(H264Dec *d, IMFSample *s, H264Pic *pic) {
    IMFMediaBuffer *b = NULL;
    if (FAILED(IMFSample_ConvertToContiguousBuffer(s, &b))) return 0;
    BYTE *p = NULL;
    DWORD len = 0;
    int ok = 0;
    if (SUCCEEDED(IMFMediaBuffer_Lock(b, &p, NULL, &len))) {
        unsigned w = d->w < d->fw ? d->w : d->fw, h = d->h < d->fh ? d->h : d->fh;
        size_t pitch = d->stride, cwid = (w + 1) / 2, chei = (h + 1) / 2;
        if ((size_t)len >= pitch * d->fh + pitch * ((d->fh + 1) / 2) - (pitch - 2 * cwid)) {
            uint8_t *o = malloc((size_t)w * h + 2 * cwid * chei);
            if (!o) rt_fatal("h264: out of memory for a %ux%u picture", w, h);
            for (unsigned y = 0; y < h; y++) memcpy(o + (size_t)y * w, p + y * pitch, w);
            const BYTE *uv = p + pitch * d->fh;
            for (size_t y = 0; y < chei; y++) memcpy(o + (size_t)w * h + y * 2 * cwid, uv + y * pitch, 2 * cwid);
            LONGLONG t = 0;
            IMFSample_GetSampleTime(s, &t);
            *pic = (H264Pic){o, (uint16_t)w, (uint16_t)h, (int64_t)t * 100};
            if (d->have_last && pic->pts < d->last_pts && d->failures++ < 4)
                rt_log("h264: picture at %lld us came out after one at %lld us (out of display order)",
                       (long long)(pic->pts / 1000), (long long)(d->last_pts / 1000));
            d->last_pts = pic->pts, d->have_last = 1;
            ok = 1;
        }
        IMFMediaBuffer_Unlock(b);
    }
    IMFMediaBuffer_Release(b);
    return ok;
}

// Pictures the decoder has ready, appended to out[*n..max).
static void drain(H264Dec *d, H264Pic *out, int *n, int max) {
    for (;;) {
        MFT_OUTPUT_STREAM_INFO info = {0};
        if (FAILED(IMFTransform_GetOutputStreamInfo(d->t, 0, &info))) return;
        IMFSample *s = NULL;
        IMFMediaBuffer *b = NULL;
        int own = !(info.dwFlags & (MFT_OUTPUT_STREAM_PROVIDES_SAMPLES | MFT_OUTPUT_STREAM_CAN_PROVIDE_SAMPLES));
        if (own) {
            if (FAILED(MFCreateSample(&s)) || FAILED(MFCreateMemoryBuffer(info.cbSize, &b))) {
                if (s) IMFSample_Release(s);
                return;
            }
            IMFSample_AddBuffer(s, b);
            IMFMediaBuffer_Release(b);
        }
        MFT_OUTPUT_DATA_BUFFER ob = {0, s, 0, NULL};
        DWORD status = 0;
        HRESULT hr = IMFTransform_ProcessOutput(d->t, 0, 1, &ob, &status);
        if (ob.pEvents) IMFCollection_Release(ob.pEvents);
        if (hr == MF_E_TRANSFORM_STREAM_CHANGE) {
            if (ob.pSample) IMFSample_Release(ob.pSample);
            if (FAILED(set_nv12_output(d))) return;
            rt_log("h264: decoder output %ux%u NV12, pitch %u", d->fw, d->fh, d->stride);
            continue;
        }
        if (SUCCEEDED(hr) && ob.pSample) {
            H264Pic pic;
            if (take(d, ob.pSample, &pic)) {
                if (*n < max) out[(*n)++] = pic;
                else free(pic.nv12), rt_log("h264: a picture past the caller's room was dropped");
            }
        }
        if (ob.pSample) IMFSample_Release(ob.pSample);
        if (FAILED(hr)) {
            if (hr != MF_E_TRANSFORM_NEED_MORE_INPUT && d->failures++ < 4)
                rt_log("h264: ProcessOutput failed (%#lx)", (unsigned long)hr);
            return;
        }
    }
}

int h264_decode(H264Dec *d, const uint8_t *data, size_t size, int64_t pts, int end, H264Pic *out, int max) {
    com_join();
    int n = 0;
    if (data && size) {
        size_t len = prepare(d, data, size);
        IMFSample *s = NULL;
        IMFMediaBuffer *b = NULL;
        BYTE *p;
        if (len && SUCCEEDED(MFCreateSample(&s)) && SUCCEEDED(MFCreateMemoryBuffer((DWORD)len, &b)) &&
            SUCCEEDED(IMFMediaBuffer_Lock(b, &p, NULL, NULL))) {
            memcpy(p, d->scratch, len);
            IMFMediaBuffer_Unlock(b);
            IMFMediaBuffer_SetCurrentLength(b, (DWORD)len);
            IMFSample_AddBuffer(s, b);
            IMFSample_SetSampleTime(s, pts / 100);
            for (int tries = 0; tries < 64; tries++) {
                HRESULT hr = IMFTransform_ProcessInput(d->t, 0, s, 0);
                if (hr != MF_E_NOTACCEPTING) {
                    if (FAILED(hr) && d->failures++ < 4) rt_log("h264: ProcessInput failed (%#lx)", (unsigned long)hr);
                    break;
                }
                int before = n;
                drain(d, out, &n, max);
                if (n == before && tries) break;
            }
        }
        if (b) IMFMediaBuffer_Release(b);
        if (s) IMFSample_Release(s);
    }
    drain(d, out, &n, max);
    if (end) {
        IMFTransform_ProcessMessage(d->t, MFT_MESSAGE_COMMAND_DRAIN, 0);
        drain(d, out, &n, max);
        d->need_header = 1;
    }
    return n;
}

void h264_flush(H264Dec *d) {
    if (!d) return;
    com_join();
    IMFTransform_ProcessMessage(d->t, MFT_MESSAGE_COMMAND_FLUSH, 0);
    d->need_header = 1, d->have_last = 0;
}

void h264_close(H264Dec *d) {
    if (!d) return;
    com_join();
    if (d->t) {
        IMFTransform_ProcessMessage(d->t, MFT_MESSAGE_NOTIFY_END_OF_STREAM, 0);
        IMFTransform_ProcessMessage(d->t, MFT_MESSAGE_NOTIFY_END_STREAMING, 0);
        IMFTransform_Release(d->t);
    }
    free(d->header);
    free(d->scratch);
    free(d);
}
