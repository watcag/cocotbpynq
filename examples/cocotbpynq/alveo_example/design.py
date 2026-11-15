"""Metadata of the example design, as `v++ --link` would record it, written as a metadata-only xclbin.

Three compute units on an HBM card: mm2s_1 reads words from HBM[0] onto a stream, addk_1 (ap_ctrl_none,
registers only) adds K, s2mm_1 writes the stream to HBM[1].  With Vitis, the same connectivity is

    [connectivity]
    nk=mm2s:1:mm2s_1
    nk=addk:1:addk_1
    nk=s2mm:1:s2mm_1
    sp=mm2s_1.src:HBM[0]
    sp=s2mm_1.dst:HBM[1]
    sc=mm2s_1.out:addk_1.x
    sc=addk_1.y:s2mm_1.in
"""
from cocotbpynq.xrt import write_xclbin

CONTROL = '<port name="s_axi_control" mode="slave" range="0x40" dataWidth="32" portType="addressable" base="0x0"/>'
XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<project name="design">
  <platform>
    <device name="fpga0">
      <core name="OCL_REGION_0" target="bitstream" type="clc_region">
        <kernel name="mm2s" language="ip" vlnv="example.org:kernel:mm2s:1.0" hwControlProtocol="ap_ctrl_hs">
          <port name="m_axi_gmem" mode="master" range="0xFFFFFFFF" dataWidth="32" portType="addressable" base="0x0"/>
          <port name="out" mode="write_only" range="" dataWidth="32" portType="stream" base=""/>
          {CONTROL}
          <arg name="src" addressQualifier="1" id="0" port="m_axi_gmem" size="0x8" offset="0x10" hostOffset="0x0" hostSize="0x8" type="int*"/>
          <arg name="out" addressQualifier="4" id="1" port="out" size="0x0" offset="0x0" hostOffset="0x0" hostSize="0x8" type="stream&lt;int&gt;&amp;"/>
          <arg name="n" addressQualifier="0" id="2" port="s_axi_control" size="0x4" offset="0x1C" hostOffset="0x0" hostSize="0x4" type="unsigned int"/>
          <instance name="mm2s_1"><addrRemap base="0x0800000" range="0x10000" port="s_axi_control"/></instance>
        </kernel>
        <kernel name="addk" language="ip" vlnv="example.org:kernel:addk:1.0" hwControlProtocol="ap_ctrl_none">
          <port name="x" mode="read_only" range="" dataWidth="32" portType="stream" base=""/>
          <port name="y" mode="write_only" range="" dataWidth="32" portType="stream" base=""/>
          {CONTROL}
          <arg name="x" addressQualifier="4" id="0" port="x" size="0x4" offset="0x0" hostOffset="0x0" hostSize="0x4" type="void*"/>
          <arg name="y" addressQualifier="4" id="1" port="y" size="0x4" offset="0x0" hostOffset="0x0" hostSize="0x4" type="void*"/>
          <instance name="addk_1"><addrRemap base="0x0810000" range="0x10000" port="s_axi_control"/></instance>
        </kernel>
        <kernel name="s2mm" language="ip" vlnv="example.org:kernel:s2mm:1.0" hwControlProtocol="ap_ctrl_hs">
          <port name="m_axi_gmem" mode="master" range="0xFFFFFFFF" dataWidth="32" portType="addressable" base="0x0"/>
          <port name="in" mode="read_only" range="" dataWidth="32" portType="stream" base=""/>
          {CONTROL}
          <arg name="in" addressQualifier="4" id="0" port="in" size="0x0" offset="0x0" hostOffset="0x0" hostSize="0x8" type="stream&lt;int&gt;&amp;"/>
          <arg name="dst" addressQualifier="1" id="1" port="m_axi_gmem" size="0x8" offset="0x10" hostOffset="0x0" hostSize="0x8" type="int*"/>
          <arg name="n" addressQualifier="0" id="2" port="s_axi_control" size="0x4" offset="0x1C" hostOffset="0x0" hostSize="0x4" type="unsigned int"/>
          <instance name="s2mm_1"><addrRemap base="0x0820000" range="0x10000" port="s_axi_control"/></instance>
        </kernel>
      </core>
    </device>
  </platform>
</project>
"""
MEMS = [{"tag": "HBM[0]", "type": "HBM", "base_address": 0x00000000, "size": 256 << 20},
        {"tag": "HBM[1]", "type": "HBM", "base_address": 0x10000000, "size": 256 << 20},
        {"tag": "dc_0", "type": "STREAMING_CONNECTION"},
        {"tag": "dc_1", "type": "STREAMING_CONNECTION"}]
CONNECTIONS = [("mm2s_1", "src", "HBM[0]"), ("s2mm_1", "dst", "HBM[1]"),
               ("mm2s_1", "out", "dc_0"), ("addk_1", "x", "dc_0"),
               ("addk_1", "y", "dc_1"), ("s2mm_1", "in", "dc_1")]

if __name__ == "__main__":
    print(write_xclbin("design.xclbin", XML, MEMS, CONNECTIONS))
