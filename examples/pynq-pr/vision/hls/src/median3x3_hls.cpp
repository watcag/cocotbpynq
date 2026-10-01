#include "vision_common.hpp"

extern "C" void median3x3_hls(
    axis_stream_t& x,
    axis_stream_t& y,
    unsigned int rows,
    unsigned int cols
) {
#pragma HLS INTERFACE axis register both port=x
#pragma HLS INTERFACE axis register both port=y
#pragma HLS INTERFACE s_axilite port=rows bundle=AXILiteS
#pragma HLS INTERFACE s_axilite port=cols bundle=AXILiteS
#pragma HLS INTERFACE s_axilite port=return bundle=AXILiteS

    gray_image_t img_in(rows, cols);
    gray_image_t img_out(rows, cols);

#pragma HLS DATAFLOW

    stream_to_gray(x, img_in, rows, cols);
    xf::cv::medianBlur<
        VISION_FILTER_SIZE,
        XF_BORDER_REPLICATE,
        XF_8UC1,
        VISION_MAX_HEIGHT,
        VISION_MAX_WIDTH,
        VISION_NPPC
    >(img_in, img_out);
    gray_to_stream(img_out, y, rows, cols);
}
