#ifndef EXAMPLES_VISION_HLS_SRC_VISION_COMMON_HPP_
#define EXAMPLES_VISION_HLS_SRC_VISION_COMMON_HPP_

#include <ap_axi_sdata.h>
#include <ap_int.h>
#include <hls_stream.h>

#include "common/xf_common.hpp"
#include "imgproc/xf_custom_convolution.hpp"
#include "imgproc/xf_median_blur.hpp"
#include "imgproc/xf_sobel.hpp"

static constexpr int VISION_MAX_HEIGHT = 1080;
static constexpr int VISION_MAX_WIDTH = 1920;
static constexpr int VISION_DATA_WIDTH = 32;
static constexpr int VISION_NPPC = XF_NPPC1;
static constexpr int VISION_FILTER_SIZE = 3;

typedef ap_axiu<VISION_DATA_WIDTH, 0, 0, 0> axis_word_t;
typedef hls::stream<axis_word_t> axis_stream_t;
typedef xf::cv::Mat<XF_8UC1, VISION_MAX_HEIGHT, VISION_MAX_WIDTH, VISION_NPPC> gray_image_t;
typedef xf::cv::Mat<XF_16SC1, VISION_MAX_HEIGHT, VISION_MAX_WIDTH, VISION_NPPC> grad_image_t;

static inline int frame_word_count(int rows, int cols) {
    return rows * cols;
}

static inline void stream_to_gray(axis_stream_t& src, gray_image_t& dst, int rows, int cols) {
    const int words = frame_word_count(rows, cols);
stream_to_gray_loop:
    for (int i = 0; i < words; ++i) {
#pragma HLS PIPELINE II=1
        axis_word_t beat = src.read();
        ap_uint<8> pixel = beat.data.range(7, 0);
        dst.write(i, pixel);
    }
}

static inline void gray_to_stream(gray_image_t& src, axis_stream_t& dst, int rows, int cols) {
    const int words = frame_word_count(rows, cols);
gray_to_stream_loop:
    for (int i = 0; i < words; ++i) {
#pragma HLS PIPELINE II=1
        axis_word_t beat;
        beat.data = 0;
        beat.data.range(7, 0) = src.read(i);
        beat.keep = -1;
        beat.strb = -1;
        beat.last = (i == words - 1);
        dst.write(beat);
    }
}

static inline ap_uint<8> clip_abs_u8(ap_int<16> value) {
    ap_uint<16> magnitude = (value < 0) ? ap_uint<16>(-value) : ap_uint<16>(value);
    if (magnitude > 255) {
        return 255;
    }
    return magnitude.range(7, 0);
}

static inline ap_uint<8> clip_mag_u8(ap_int<16> gx, ap_int<16> gy) {
    ap_uint<16> ax = (gx < 0) ? ap_uint<16>(-gx) : ap_uint<16>(gx);
    ap_uint<16> ay = (gy < 0) ? ap_uint<16>(-gy) : ap_uint<16>(gy);
    ap_uint<17> magnitude = ax + ay;
    if (magnitude > 255) {
        return 255;
    }
    return magnitude.range(7, 0);
}

static inline void grad_abs_to_gray(grad_image_t& src, gray_image_t& dst, int rows, int cols) {
    const int words = frame_word_count(rows, cols);
grad_abs_to_gray_loop:
    for (int i = 0; i < words; ++i) {
#pragma HLS PIPELINE II=1
        ap_int<16> value = src.read(i);
        dst.write(i, clip_abs_u8(value));
    }
}

static inline void sobel_mag_to_gray(
    grad_image_t& grad_x,
    grad_image_t& grad_y,
    gray_image_t& dst,
    int rows,
    int cols
) {
    const int words = frame_word_count(rows, cols);
sobel_mag_to_gray_loop:
    for (int i = 0; i < words; ++i) {
#pragma HLS PIPELINE II=1
        ap_int<16> gx = grad_x.read(i);
        ap_int<16> gy = grad_y.read(i);
        dst.write(i, clip_mag_u8(gx, gy));
    }
}

#endif  // EXAMPLES_VISION_HLS_SRC_VISION_COMMON_HPP_
