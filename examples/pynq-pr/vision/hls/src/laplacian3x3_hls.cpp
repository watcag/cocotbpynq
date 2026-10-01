#include "vision_common.hpp"

extern "C" void laplacian3x3_hls(
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
    grad_image_t lap(rows, cols);
    short kernel[VISION_FILTER_SIZE * VISION_FILTER_SIZE] = {
         0,  1,  0,
         1, -4,  1,
         0,  1,  0,
    };

#pragma HLS ARRAY_PARTITION variable=kernel complete
#pragma HLS DATAFLOW

    stream_to_gray(x, img_in, rows, cols);
    xf::cv::filter2D<
        XF_BORDER_CONSTANT,
        VISION_FILTER_SIZE,
        VISION_FILTER_SIZE,
        XF_8UC1,
        XF_16SC1,
        VISION_MAX_HEIGHT,
        VISION_MAX_WIDTH,
        VISION_NPPC
    >(img_in, lap, kernel, 0);
    grad_abs_to_gray(lap, img_out, rows, cols);
    gray_to_stream(img_out, y, rows, cols);
}
