#include "vision_common.hpp"

extern "C" void sobel_mag_hls(
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
    grad_image_t grad_x(rows, cols);
    grad_image_t grad_y(rows, cols);

#pragma HLS DATAFLOW

    stream_to_gray(x, img_in, rows, cols);
    xf::cv::Sobel<
        XF_BORDER_CONSTANT,
        XF_FILTER_3X3,
        XF_8UC1,
        XF_16SC1,
        VISION_MAX_HEIGHT,
        VISION_MAX_WIDTH,
        VISION_NPPC
    >(img_in, grad_x, grad_y);
    sobel_mag_to_gray(grad_x, grad_y, img_out, rows, cols);
    gray_to_stream(img_out, y, rows, cols);
}
