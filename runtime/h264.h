// H.264 decoding on the host for nn::codec's H264Decoder (ov_codec.c). Windows: Media Foundation's H.264 decoder
// (h264_win.c, part of Windows, nothing to ship); elsewhere no decoder yet (h264_sdl.c): h264_open fails.
#pragma once
#include <stddef.h>
#include <stdint.h>

typedef struct H264Dec H264Dec;

// A decoded picture: packed NV12 (w*h luma, then ceil(w/2)*ceil(h/2) interleaved UV pairs), malloc'd, the caller frees.
typedef struct {
    uint8_t *nv12;
    uint16_t w, h;
    int64_t pts;   // nanoseconds, as submitted
} H264Pic;

// config: what the game passed to InitializeH264Decoder (an avcC record, or Annex B SPS/PPS); may be empty. Packets may
// be Annex B or length-prefixed (the avcC's length size, else 4 bytes). NULL if no decoder can start.
H264Dec *h264_open(unsigned w, unsigned h, const uint8_t *config, size_t config_size);
// Decodes one packet (size 0: none); end drains the decoder. Up to max pictures that came out, in display order, go to
// out; returns how many (pictures past max are dropped, which the caller avoids by passing room for the delay).
int h264_decode(H264Dec *d, const uint8_t *data, size_t size, int64_t pts, int end, H264Pic *out, int max);
void h264_flush(H264Dec *d);   // drops pictures and packets in flight; the next packet starts afresh (a key frame)
void h264_close(H264Dec *d);
const char *h264_backend(void);
