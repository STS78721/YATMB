// H.264 off Windows: no host decoder yet, so InitializeH264Decoder reports the decoder as unavailable (h264.h).
#include "h264.h"

H264Dec *h264_open(unsigned w, unsigned h, const uint8_t *config, size_t config_size) {
    (void)w, (void)h, (void)config, (void)config_size;
    return NULL;
}
int h264_decode(H264Dec *d, const uint8_t *data, size_t size, int64_t pts, int end, H264Pic *out, int max) {
    (void)d, (void)data, (void)size, (void)pts, (void)end, (void)out, (void)max;
    return 0;
}
void h264_flush(H264Dec *d) { (void)d; }
void h264_close(H264Dec *d) { (void)d; }
const char *h264_backend(void) { return "none on this OS"; }
