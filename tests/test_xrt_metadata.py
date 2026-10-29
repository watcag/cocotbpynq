"""Device-free register-control metadata and real RTL parser checks."""
import tempfile
import unittest
from pathlib import Path

from cocotbpynq.xrt import _module_ports, describe, read_xclbin, write_xclbin


class MetadataTests(unittest.TestCase):
    def test_control_protocol_roundtrip(self):
        for protocol, encoded in [('user_managed','ap_ctrl_none'),('ap_ctrl_none','ap_ctrl_none'),
                                  ('ap_ctrl_hs','ap_ctrl_hs'),('ap_ctrl_chain','ap_ctrl_chain')]:
            with self.subTest(protocol=protocol), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'metadata.xclbin'
                xml = ('<project><kernel name="register_device" hwControlProtocol="'+protocol+'">'
                       '<instance name="register_device_1"><addrRemap base="0x10000" range="0x100"/>'
                       '</instance></kernel></project>')
                write_xclbin(path,xml,[],[])
                _,root,_,ips,_ = read_xclbin(path)
                self.assertEqual(ips[0]['control'],encoded)
                self.assertEqual(next(root.iter('kernel')).get('hwControlProtocol'),protocol)
                device = describe(path)[0]['register_device_1']
                self.assertEqual(device['hw_control_protocol'],protocol)
                self.assertEqual('CTRL' in device['registers'],protocol in ('ap_ctrl_hs','ap_ctrl_chain'))

    def test_unknown_control_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'metadata.xclbin'
            with self.assertRaises(KeyError):
                write_xclbin(path,'<project><kernel name="bad" hwControlProtocol="unknown"/></project>',[],[])
            self.assertFalse(path.exists())

    def test_installed_pyslang_parses_real_ports(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'tiny.sv'
            source.write_text('module tiny(input wire clk, input wire [63:0] value, output wire [7:0] result); assign result=value[7:0]; endmodule\n')
            self.assertEqual(_module_ports([source],['tiny'])['tiny'],
                             {'clk':('input',1),'value':('input',64),'result':('output',8)})


if __name__ == '__main__':
    unittest.main()
