"""
Auto-generates the static region SystemVerilog module from PR config.

Supports:
- Multiple partitions with independent DMAs
- Optional AXI-Stream switch for runtime pipeline routing
- Per-partition simple-boundary FSMs and full-AXI stream adapters
"""
from pathlib import Path
from typing import Dict, List, Any
import logging
import re

logger = logging.getLogger(__name__)

_FULL_AXI_WIRED_TO_RM = {
    'rst_n',
    'x_TDATA',
    'x_TVALID',
    'x_TLAST',
    'y_TREADY',
    's_axi_AXILiteS_AWVALID',
    's_axi_AXILiteS_AWADDR',
    's_axi_AXILiteS_WVALID',
    's_axi_AXILiteS_WDATA',
    's_axi_AXILiteS_WSTRB',
    's_axi_AXILiteS_ARVALID',
    's_axi_AXILiteS_ARADDR',
    's_axi_AXILiteS_RREADY',
    's_axi_AXILiteS_BREADY',
}


def _stream0_name(name: str) -> str:
    """x1_TDATA -> x_TDATA: stream k of a partition uses the stream-0 rules."""
    return re.sub(r'^([xy])\d+_', r'\1_', name)


def _find_port(boundary: List[Dict[str, Any]], name: str, direction: str = None):
    for port in boundary:
        if port.get('name') != name:
            continue
        if direction is None or port.get('direction') == direction:
            return port
    return None


def _uses_full_axi_boundary(boundary: List[Dict[str, Any]]) -> bool:
    required = {
        ('rst_n', 'to_rm'),
        ('x_TDATA', 'to_rm'),
        ('x_TVALID', 'to_rm'),
        ('x_TREADY', 'from_rm'),
        ('x_TLAST', 'to_rm'),
        ('y_TDATA', 'from_rm'),
        ('y_TVALID', 'from_rm'),
        ('y_TREADY', 'to_rm'),
        ('y_TLAST', 'from_rm'),
    }
    present = {(p.get('name'), p.get('direction')) for p in boundary}
    return required.issubset(present)


def _emit_axilite_tieoffs(a, prefix, to_rm, indent):
    tieoffs = [
        ('s_axi_AXILiteS_AWVALID', '0'),
        ('s_axi_AXILiteS_AWADDR', '0'),
        ('s_axi_AXILiteS_WVALID', '0'),
        ('s_axi_AXILiteS_WDATA', '0'),
        ('s_axi_AXILiteS_WSTRB', '0'),
        ('s_axi_AXILiteS_ARVALID', '0'),
        ('s_axi_AXILiteS_ARADDR', '0'),
        ('s_axi_AXILiteS_RREADY', '1'),
        ('s_axi_AXILiteS_BREADY', '1'),
    ]
    for sig, val in tieoffs:
        if _find_port(to_rm, sig):
            a(f"{indent}{prefix}_{sig} <= {val};")


def _emit_axilite_assigns(a, prefix, to_rm, indent):
    tieoffs = [
        ('s_axi_AXILiteS_AWVALID', '0'),
        ('s_axi_AXILiteS_AWADDR', '0'),
        ('s_axi_AXILiteS_WVALID', '0'),
        ('s_axi_AXILiteS_WDATA', '0'),
        ('s_axi_AXILiteS_WSTRB', '0'),
        ('s_axi_AXILiteS_ARVALID', '0'),
        ('s_axi_AXILiteS_ARADDR', '0'),
        ('s_axi_AXILiteS_RREADY', '1'),
        ('s_axi_AXILiteS_BREADY', '1'),
    ]
    for sig, val in tieoffs:
        if _find_port(to_rm, sig):
            a(f"{indent}assign {prefix}_{sig} = {val};")


_AXIL_TO_RM = {
    'awvalid': 's_axi_AXILiteS_AWVALID',
    'awaddr': 's_axi_AXILiteS_AWADDR',
    'wvalid': 's_axi_AXILiteS_WVALID',
    'wdata': 's_axi_AXILiteS_WDATA',
    'wstrb': 's_axi_AXILiteS_WSTRB',
    'arvalid': 's_axi_AXILiteS_ARVALID',
    'araddr': 's_axi_AXILiteS_ARADDR',
    'rready': 's_axi_AXILiteS_RREADY',
    'bready': 's_axi_AXILiteS_BREADY',
}

_AXIL_FROM_RM = {
    'awready': 's_axi_AXILiteS_AWREADY',
    'wready': 's_axi_AXILiteS_WREADY',
    'arready': 's_axi_AXILiteS_ARREADY',
    'rvalid': 's_axi_AXILiteS_RVALID',
    'rdata': 's_axi_AXILiteS_RDATA',
    'rresp': 's_axi_AXILiteS_RRESP',
    'bvalid': 's_axi_AXILiteS_BVALID',
    'bresp': 's_axi_AXILiteS_BRESP',
}


def _iface_port_prefix(iface_name: str, iface_def: Dict[str, Any]) -> str:
    return iface_def.get('port_prefix', iface_name)


def _emit_axilite_connections(a, rm_prefix, axil_prefix, to_rm, from_rm, indent):
    for axil_sig, rm_sig in _AXIL_TO_RM.items():
        port = _find_port(to_rm, rm_sig)
        if not port:
            continue
        width = port.get('width', 1)
        source = f"{axil_prefix}_{axil_sig}"
        if width < 32 and axil_sig in ('awaddr', 'araddr', 'wdata'):
            source = f"{source}[{width - 1}:0]"
        a(f"{indent}assign {rm_prefix}_{rm_sig} = {source};")

    for axil_sig, rm_sig in _AXIL_FROM_RM.items():
        if _find_port(from_rm, rm_sig):
            a(f"{indent}assign {axil_prefix}_{axil_sig} = {rm_prefix}_{rm_sig};")


def generate_static_region(
    design_name: str,
    clock_name: str,
    reset_name: str,
    partitions: List[Dict[str, Any]],
    interfaces: Dict[str, Any],
    build_dir: str,
    axis_switch_source: str = None,
    fsm_wait_cycles: int = 7,
) -> Path:
    """Generate static region SV file.

    Parameters
    ----------
    design_name : str
        Module name for the static region.
    clock_name : str
        Clock signal name.
    reset_name : str or None
        Reset signal name (active-low assumed).
    partitions : list
        Partition configs from YAML (name, rm_module, boundary, etc.).
    interfaces : dict
        Interface configs from YAML static_region.interfaces.
    build_dir : str
        Output directory.
    axis_switch_source : str or None
        Path to axis_switch.sv if switch is needed.

    Returns
    -------
    Path
        Path to generated SV file.
    """
    # Detect switch from interfaces
    switch_iface = None
    for iface_name, iface_def in interfaces.items():
        if iface_def.get('type') == 'axil' and 'switch' in iface_name.lower():
            switch_iface = iface_name
            break
    has_switch = switch_iface is not None
    axil_ifaces = [
        (iface_name, iface_def)
        for iface_name, iface_def in interfaces.items()
        if iface_def.get('type') == 'axil'
    ]

    # Build partition info
    parts = []
    for idx, part_cfg in enumerate(partitions):
        # Find DMA interfaces for this partition (by order)
        sb_ifaces = [(n, d) for n, d in interfaces.items() if d.get('type') == 'sb']
        # Group by dma_instance
        dma_instances = []
        seen = set()
        for n, d in sb_ifaces:
            inst = d.get('dma_instance', f'axi_dma_{idx}')
            if inst not in seen:
                dma_instances.append(inst)
                seen.add(inst)

        # This partition's DMAs: those whose interfaces name it ('partition'), in order,
        # else the idx-th DMA.  DMA k drives the RM's x<k>/y<k> (x/y for k = 0).
        part_dmas = [i for i in dma_instances
                     if any(d.get('dma_instance') == i and d.get('partition') == part_cfg['name'] for _, d in sb_ifaces)]
        if not part_dmas and idx < len(dma_instances):
            part_dmas = [dma_instances[idx]]
        streams = []
        for k, target_dma in enumerate(part_dmas):
            s = {'tag': f'{idx}' if k == 0 else f'{idx}s{k}', 'x': 'x' if k == 0 else f'x{k}',
                 'y': 'y' if k == 0 else f'y{k}', 'dma_in': None, 'dma_out': None}
            for n, d in sb_ifaces:
                if d.get('dma_instance') == target_dma:
                    if d.get('direction') in ('subordinate', 'input'):
                        s['dma_in'], s['dma_in_def'] = n, d
                    elif d.get('direction') in ('manager', 'output'):
                        s['dma_out'], s['dma_out_def'] = n, d
            streams.append(s)
        s0 = streams[0] if streams else {}
        dma_in, dma_out = s0.get('dma_in'), s0.get('dma_out')
        dma_in_def, dma_out_def = s0.get('dma_in_def'), s0.get('dma_out_def')

        axil_iface = None
        for n, d in axil_ifaces:
            if d.get('partition') == part_cfg['name']:
                axil_iface = (n, d)
                break

        boundary = part_cfg.get('boundary', [])
        to_rm = [p for p in boundary if p['direction'] == 'to_rm']
        from_rm = [p for p in boundary if p['direction'] == 'from_rm']
        x_tdata = _find_port(boundary, 'x_TDATA', 'to_rm')
        y_tdata = _find_port(boundary, 'y_TDATA', 'from_rm')
        dw = (
            (dma_in_def or {}).get('dw')
            or (dma_out_def or {}).get('dw')
            or (x_tdata or {}).get('width')
            or (y_tdata or {}).get('width')
            or (to_rm[0].get('width', 32) if to_rm else 32)
        )

        parts.append({
            'name': part_cfg['name'],
            'rm_module': part_cfg.get('rm_module', f"rm_{idx}"),
            'prefix': part_cfg['name'],
            'dma_in': dma_in or f'x{idx}',
            'dma_out': dma_out or f'y{idx}',
            'dw': dw,
            'to_rm': to_rm,
            'from_rm': from_rm,
            'full_axi_boundary': _uses_full_axi_boundary(boundary),
            'axil_iface': axil_iface,
            'axil_prefix': _iface_port_prefix(*axil_iface) if axil_iface else None,
            'idx': idx,
            'streams': streams[1:],
        })

    num_ports = 2 * len(parts)
    lines = []
    a = lines.append

    a(f"`timescale 1ns/1ps")
    a(f"// Auto-generated static region: {len(parts)} partition(s), "
      f"{'with' if has_switch else 'without'} switch.")
    a(f"")
    a(f"module {design_name} (")
    a(f"    input  wire        {clock_name},")
    if reset_name:
        a(f"    input  wire        {reset_name},")

    if axil_ifaces:
        a(f"")
        # AXI-Lite port block
        axil_sigs = [
            ('input',  '[31:0]', 'awaddr'), ('input',  '',       'awvalid'), ('output', '',       'awready'),
            ('input',  '[31:0]', 'wdata'),  ('input',  '[3:0]',  'wstrb'),   ('input',  '',       'wvalid'),
            ('output', '',       'wready'), ('output', '[1:0]',  'bresp'),   ('output', '',       'bvalid'),
            ('input',  '',       'bready'),
            ('input',  '[31:0]', 'araddr'), ('input',  '',       'arvalid'), ('output', '',       'arready'),
            ('output', '[31:0]', 'rdata'),  ('output', '[1:0]',  'rresp'),   ('output', '',       'rvalid'),
            ('input',  '',       'rready'),
        ]
        for iface_name, iface_def in axil_ifaces:
            axil_prefix = _iface_port_prefix(iface_name, iface_def)
            for direction, width, sig in axil_sigs:
                w = f"{width:6s} " if width else "       "
                a(f"    {direction:6s} wire {w}{axil_prefix}_{sig},")

    a(f"")
    for pi, p in enumerate(parts):
        dw = p['dw']
        dmas = [(p['dma_in'], p['dma_out'], f"DMA{pi} ({p['name']})")] + [
            (s['dma_in'], s['dma_out'], f"DMA{pi} stream {s['x']}/{s['y']} ({p['name']})") for s in p['streams']]
        for k, (din, dout, label) in enumerate(dmas):
            a(f"    // {label}")
            a(f"    input  wire [{dw-1}:0] {din}_tdata,")
            a(f"    input  wire        {din}_tvalid,")
            a(f"    output wire        {din}_tready,")
            a(f"    input  wire        {din}_tlast,")
            a(f"    output wire [{dw-1}:0] {dout}_tdata,")
            a(f"    output wire        {dout}_tvalid,")
            a(f"    input  wire        {dout}_tready,")
            comma = "," if k < len(dmas) - 1 or pi < len(parts) - 1 else ""
            a(f"    output wire        {dout}_tlast{comma}")
        if pi < len(parts) - 1:
            a(f"")

    a(f");")
    a(f"")

    # RM boundaries
    for p in parts:
        a(f"    // ── {p['name']} RM boundary ──")
        for port in p['to_rm']:
            w = port.get('width', 32)
            decl = "reg "
            if p['full_axi_boundary'] and _stream0_name(port['name']) in _FULL_AXI_WIRED_TO_RM:
                decl = "wire"
            a(f"    {decl:4s} [{w-1}:0] {p['prefix']}_{port['name']};")
        for port in p['from_rm']:
            w = port.get('width', 32)
            a(f"    wire [{w-1}:0] {p['prefix']}_{port['name']};")
        a(f"")
        conns = [f"        .{clock_name}({clock_name})"]
        for port in p['to_rm']:
            conns.append(f"        .{port['name']}({p['prefix']}_{port['name']})")
        for port in p['from_rm']:
            conns.append(f"        .{port['name']}({p['prefix']}_{port['name']})")
        a(f"    {p['rm_module']} u_{p['prefix']} (")
        a(",\n".join(conns))
        a(f"    );")
        a(f"")

    if has_switch:
        # Switch wiring
        a(f"    // ── Switch wiring ──")
        for pi, p in enumerate(parts):
            a(f"    wire [{p['dw']-1}:0] fsm{pi}_in_tdata, fsm{pi}_out_tdata;")
            a(f"    wire        fsm{pi}_in_tvalid, fsm{pi}_in_tready, fsm{pi}_in_tlast;")
            a(f"    wire        fsm{pi}_out_tvalid, fsm{pi}_out_tready, fsm{pi}_out_tlast;")
        a(f"")

        # Slave bus concatenation: {port_N_hi, ..., port_0_lo}
        # Port 2*i = RP output, Port 2*i+1 = DMA MM2S
        s_tdata_parts = []
        s_tvalid_parts = []
        s_tlast_parts = []
        s_tready_parts = []
        for pi in reversed(range(len(parts))):
            p = parts[pi]
            s_tdata_parts.extend([f"{p['dma_in']}_tdata", f"fsm{pi}_out_tdata"])
            s_tvalid_parts.extend([f"{p['dma_in']}_tvalid", f"fsm{pi}_out_tvalid"])
            s_tlast_parts.extend([f"{p['dma_in']}_tlast", f"fsm{pi}_out_tlast"])
            s_tready_parts.extend([f"{p['dma_in']}_tready", f"fsm{pi}_out_tready"])

        a(f"    wire [{num_ports}*{parts[0]['dw']}-1:0] sw_s_tdata;")
        a(f"    wire [{num_ports}-1:0] sw_s_tvalid, sw_s_tready, sw_s_tlast;")
        a(f"    wire [{num_ports}*{parts[0]['dw']}-1:0] sw_m_tdata;")
        a(f"    wire [{num_ports}-1:0] sw_m_tvalid, sw_m_tready, sw_m_tlast;")
        a(f"")
        a(f"    assign sw_s_tdata = {{{', '.join(s_tdata_parts)}}};")
        a(f"    assign sw_s_tvalid = {{{', '.join(s_tvalid_parts)}}};")
        a(f"    assign sw_s_tlast = {{{', '.join(s_tlast_parts)}}};")
        a(f"    assign {{{', '.join(s_tready_parts)}}} = sw_s_tready;")
        a(f"")

        # Master bus
        m_tdata_parts = []
        m_tvalid_parts = []
        m_tlast_parts = []
        m_tready_parts = []
        for pi in reversed(range(len(parts))):
            p = parts[pi]
            m_tdata_parts.extend([f"{p['dma_out']}_tdata", f"fsm{pi}_in_tdata"])
            m_tvalid_parts.extend([f"{p['dma_out']}_tvalid", f"fsm{pi}_in_tvalid"])
            m_tlast_parts.extend([f"{p['dma_out']}_tlast", f"fsm{pi}_in_tlast"])
            m_tready_parts.extend([f"{p['dma_out']}_tready", f"fsm{pi}_in_tready"])

        a(f"    assign {{{', '.join(m_tdata_parts)}}} = sw_m_tdata;")
        a(f"    assign {{{', '.join(m_tvalid_parts)}}} = sw_m_tvalid;")
        a(f"    assign {{{', '.join(m_tlast_parts)}}} = sw_m_tlast;")
        a(f"    assign sw_m_tready = {{{', '.join(m_tready_parts)}}};")
        a(f"")

        # Switch instance
        rst = reset_name if reset_name else "1'b1"
        a(f"    axis_switch #(.NUM_PORTS({num_ports}), .TDATA_WIDTH({parts[0]['dw']})) u_switch (")
        a(f"        .aclk({clock_name}), .aresetn({rst}),")
        switch_prefix = _iface_port_prefix(switch_iface, interfaces[switch_iface])
        for sig in ['awaddr', 'awvalid', 'awready', 'wdata', 'wstrb', 'wvalid', 'wready',
                    'bresp', 'bvalid', 'bready', 'araddr', 'arvalid', 'arready',
                    'rdata', 'rresp', 'rvalid', 'rready']:
            src = f"{switch_prefix}_{sig}"
            if sig in ('awaddr', 'araddr'):
                src = f"{src}[7:0]"
            a(f"        .s_axi_ctrl_{sig}({src}),")
        a(f"        .s_axis_tdata(sw_s_tdata), .s_axis_tvalid(sw_s_tvalid),")
        a(f"        .s_axis_tready(sw_s_tready), .s_axis_tlast(sw_s_tlast),")
        a(f"        .m_axis_tdata(sw_m_tdata), .m_axis_tvalid(sw_m_tvalid),")
        a(f"        .m_axis_tready(sw_m_tready), .m_axis_tlast(sw_m_tlast)")
        a(f"    );")
        a(f"")

    # Per-partition FSMs
    a(f"    localparam S_IDLE = 2'd0, S_WAIT = 2'd1, S_OUTPUT = 2'd2;")
    a(f"")

    for pi, p in enumerate(parts):
        if has_switch:
            in_pre = f"fsm{pi}_in"
            out_pre = f"fsm{pi}_out"
        else:
            in_pre = p['dma_in']
            out_pre = p['dma_out']

        to_port = p['to_rm'][0]['name'] if p['to_rm'] else 'data_in'
        from_port = p['from_rm'][0]['name'] if p['from_rm'] else 'result'
        rst_cond = f"!{reset_name}" if reset_name else "0"
        rst_guard = reset_name if reset_name else "1'b1"

        if p['full_axi_boundary']:
            # one adapter per stream: x/y with the partition's first DMA, x<k>/y<k> with its k-th
            for tag, in_pre, out_pre, xs, ys in [(pi, in_pre, out_pre, 'x', 'y')] + [
                    (s['tag'], s['dma_in'], s['dma_out'], s['x'], s['y']) for s in p['streams']]:
                first = xs == 'x'
                a(f"    // AXI adapter {tag} ({p['name']})")
                a(f"    reg [{p['dw']-1}:0] inq{tag}_data [0:1];")
                a(f"    reg                  inq{tag}_last [0:1];")
                a(f"    reg                  inq{tag}_rd, inq{tag}_wr;")
                a(f"    reg [1:0]            inq{tag}_count;")
                # The DPI boundary delivers each side's signals a cycle late, so a
                # stream handshake cannot span it.  Beats cross as one-cycle TVALID
                # pulses; TREADY across the boundary is a credit (room for the beats
                # in flight), and the RM-side wrapper does the RM's real handshake.
                a(f"    reg [{p['dw']-1}:0] outq{tag}_data [0:15];")
                a(f"    reg                  outq{tag}_last [0:15];")
                a(f"    reg [3:0]            outq{tag}_rd, outq{tag}_wr;")
                a(f"    reg [4:0]            outq{tag}_count;")
                a(f"    wire                 inq{tag}_push = {in_pre}_tvalid & {in_pre}_tready;")
                a(f"    wire                 inq{tag}_pop = (inq{tag}_count != 0) & {p['prefix']}_{xs}_TREADY;")
                a(f"    wire                 outq{tag}_push = {p['prefix']}_{ys}_TVALID;")
                a(f"    wire                 outq{tag}_pop = (outq{tag}_count != 0) & {out_pre}_tready;")
                a(f"")
                a(f"    assign {in_pre}_tready  = (inq{tag}_count != 2) & {rst_guard};")
                a(f"    assign {out_pre}_tdata  = (outq{tag}_count != 0) ? outq{tag}_data[outq{tag}_rd] : {p['dw']}'d0;")
                a(f"    assign {out_pre}_tvalid = (outq{tag}_count != 0);")
                a(f"    assign {out_pre}_tlast  = (outq{tag}_count != 0) ? outq{tag}_last[outq{tag}_rd] : 1'b0;")
                if first and _find_port(p['to_rm'], 'rst_n', 'to_rm'):
                    a(f"    assign {p['prefix']}_rst_n = {rst_guard};")
                if _find_port(p['to_rm'], f'{xs}_TDATA', 'to_rm'):
                    a(f"    assign {p['prefix']}_{xs}_TDATA = (inq{tag}_count != 0) ? inq{tag}_data[inq{tag}_rd] : {p['dw']}'d0;")
                if _find_port(p['to_rm'], f'{xs}_TVALID', 'to_rm'):
                    a(f"    assign {p['prefix']}_{xs}_TVALID = inq{tag}_pop;")
                if _find_port(p['to_rm'], f'{xs}_TLAST', 'to_rm'):
                    a(f"    assign {p['prefix']}_{xs}_TLAST = (inq{tag}_count != 0) ? inq{tag}_last[inq{tag}_rd] : 1'b0;")
                if _find_port(p['to_rm'], f'{ys}_TREADY', 'to_rm'):
                    a(f"    assign {p['prefix']}_{ys}_TREADY = (outq{tag}_count <= 8);")
                if first and p['axil_prefix']:
                    _emit_axilite_connections(a, p['prefix'], p['axil_prefix'], p['to_rm'], p['from_rm'], "    ")
                elif first:
                    _emit_axilite_assigns(a, p['prefix'], p['to_rm'], "    ")
                a(f"")
                a(f"    always @(posedge {clock_name}) begin")
                a(f"        if ({rst_cond}) begin")
                a(f"            inq{tag}_rd <= 0; inq{tag}_wr <= 0; inq{tag}_count <= 0;")
                a(f"            outq{tag}_rd <= 0; outq{tag}_wr <= 0; outq{tag}_count <= 0;")
                a(f"            inq{tag}_data[0] <= 0; inq{tag}_data[1] <= 0;")
                a(f"            inq{tag}_last[0] <= 0; inq{tag}_last[1] <= 0;")
                a(f"        end else begin")
                a(f"            if (inq{tag}_push) begin")
                a(f"                inq{tag}_data[inq{tag}_wr] <= {in_pre}_tdata;")
                a(f"                inq{tag}_last[inq{tag}_wr] <= {in_pre}_tlast;")
                a(f"                inq{tag}_wr <= ~inq{tag}_wr;")
                a(f"            end")
                a(f"            if (inq{tag}_pop) begin")
                a(f"                inq{tag}_rd <= ~inq{tag}_rd;")
                a(f"            end")
                a(f"            case ({{inq{tag}_push, inq{tag}_pop}})")
                a(f"                2'b10: inq{tag}_count <= inq{tag}_count + 1'b1;")
                a(f"                2'b01: inq{tag}_count <= inq{tag}_count - 1'b1;")
                a(f"                default: inq{tag}_count <= inq{tag}_count;")
                a(f"            endcase")
                a(f"")
                a(f"            if (outq{tag}_push) begin")
                a(f"                outq{tag}_data[outq{tag}_wr] <= {p['prefix']}_{ys}_TDATA;")
                if _find_port(p['from_rm'], f'{ys}_TLAST', 'from_rm'):
                    a(f"                outq{tag}_last[outq{tag}_wr] <= {p['prefix']}_{ys}_TLAST;")
                else:
                    a(f"                outq{tag}_last[outq{tag}_wr] <= 1'b0;")
                a(f"                outq{tag}_wr <= outq{tag}_wr + 1'b1;")
                a(f"            end")
                a(f"            if (outq{tag}_pop) begin")
                a(f"                outq{tag}_rd <= outq{tag}_rd + 1'b1;")
                a(f"            end")
                a(f"            case ({{outq{tag}_push, outq{tag}_pop}})")
                a(f"                2'b10: outq{tag}_count <= outq{tag}_count + 1'b1;")
                a(f"                2'b01: outq{tag}_count <= outq{tag}_count - 1'b1;")
                a(f"                default: outq{tag}_count <= outq{tag}_count;")
                a(f"            endcase")
                a(f"        end")
                a(f"    end")
        else:
            a(f"    // FSM {pi} ({p['name']})")
            a(f"    reg [1:0] st{pi};  reg [3:0] wc{pi};  reg last{pi};")
            a(f"    reg [{p['dw']-1}:0] out{pi}_tdata;  reg out{pi}_tvalid, out{pi}_tlast;")
            a(f"")
            a(f"    assign {in_pre}_tready  = (st{pi} == S_IDLE) & {rst_guard};")
            a(f"    assign {out_pre}_tdata  = out{pi}_tdata;")
            a(f"    assign {out_pre}_tvalid = out{pi}_tvalid;")
            a(f"    assign {out_pre}_tlast  = out{pi}_tlast;")
            a(f"")
            a(f"    always @(posedge {clock_name}) begin")
            a(f"        if ({rst_cond}) begin")
            a(f"            st{pi} <= S_IDLE; wc{pi} <= 0; out{pi}_tvalid <= 0;")
            a(f"            out{pi}_tdata <= 0; out{pi}_tlast <= 0;")
            a(f"            {p['prefix']}_{to_port} <= 0; last{pi} <= 0;")
            a(f"        end else case (st{pi})")
            a(f"            S_IDLE: begin")
            a(f"                out{pi}_tvalid <= 0;")
            a(f"                if ({in_pre}_tvalid & {in_pre}_tready) begin")
            a(f"                    {p['prefix']}_{to_port} <= {in_pre}_tdata;")
            a(f"                    last{pi} <= {in_pre}_tlast;")
            a(f"                    wc{pi} <= 0; st{pi} <= S_WAIT;")
            a(f"                end")
            a(f"            end")
            a(f"            S_WAIT: begin")
            a(f"                wc{pi} <= wc{pi} + 1;")
            a(f"                if (wc{pi} == 4'd{fsm_wait_cycles}) begin")
            a(f"                    out{pi}_tdata <= {p['prefix']}_{from_port};")
            a(f"                    out{pi}_tvalid <= 1; out{pi}_tlast <= last{pi};")
            a(f"                    st{pi} <= S_OUTPUT;")
            a(f"                end")
            a(f"            end")
            a(f"            S_OUTPUT: if ({out_pre}_tready) begin out{pi}_tvalid <= 0; st{pi} <= S_IDLE; end")
            a(f"            default: st{pi} <= S_IDLE;")
            a(f"        endcase")
            a(f"    end")
        a(f"")

    a(f"endmodule")

    out_dir = Path(build_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{design_name}.sv"
    out_path.write_text("\n".join(lines))
    logger.info(f"Generated static region: {out_path}")
    return out_path
