"""Convert Nexmon CSI pcap captures to MATLAB .mat files without MATLAB."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


PCAP_MAGIC_ENDIAN = {
    b"\xd4\xc3\xb2\xa1": "<",
    b"\xa1\xb2\xc3\xd4": ">",
    b"\x4d\x3c\xb2\xa1": "<",
    b"\xa1\xb2\x3c\x4d": ">",
}

MI_INT8 = 1
MI_INT32 = 5
MI_UINT32 = 6
MI_DOUBLE = 9
MI_UINT16 = 4
MI_MATRIX = 14

MX_CHAR_CLASS = 4
MX_DOUBLE_CLASS = 6
MX_COMPLEX = 0x0800


def _nfft_from_bw(bw_mhz):
    if bw_mhz not in (20, 80):
        raise ValueError("Only 20 MHz and 80 MHz captures are supported.")
    return int(round(bw_mhz * 3.2))


def _valid_subcarrier_indexes(bw_mhz):
    if bw_mhz == 20:
        ranges = (range(5, 33), range(34, 62))
    elif bw_mhz == 80:
        ranges = (range(7, 129), range(132, 252))
    else:
        raise ValueError("Only 20 MHz and 80 MHz captures are supported.")
    return [idx - 1 for one_based in ranges for idx in one_based]


def iter_pcap_frames(filename):
    """Yield classic pcap frames with payload bytes and original length."""
    with Path(filename).open("rb") as handle:
        magic = handle.read(4)
        if magic not in PCAP_MAGIC_ENDIAN:
            raise ValueError(f"{filename} is not a classic pcap file.")
        endian = PCAP_MAGIC_ENDIAN[magic]
        header_rest = handle.read(20)
        if len(header_rest) != 20:
            raise ValueError("Truncated pcap global header.")

        packet_header = struct.Struct(f"{endian}IIII")
        while True:
            raw_header = handle.read(packet_header.size)
            if not raw_header:
                break
            if len(raw_header) != packet_header.size:
                raise ValueError("Truncated pcap packet header.")
            _ts_sec, _ts_usec, incl_len, orig_len = packet_header.unpack(raw_header)
            payload = handle.read(incl_len)
            if len(payload) != incl_len:
                raise ValueError("Truncated pcap packet payload.")
            yield {"orig_len": orig_len, "payload": payload}


def _payload_words(payload):
    """Match readpcap.m behavior: 4-byte-aligned payloads are uint32 words."""
    word_count = len(payload) // 4
    return list(struct.unpack(f"<{word_count}I", payload[: word_count * 4]))


def _unpack_float_acphy(format_id, nfft, words):
    if format_id == 0:
        nbits, nman, nexp = 10, 9, 5
    elif format_id == 1:
        nbits, nman, nexp = 10, 12, 6
    else:
        raise ValueError("format_id must be 0 for 4358 or 1 for 4366c0.")

    sign_marker = 1 << 31
    iq_mask = (1 << (nman - 1)) - 1
    e_mask = (1 << nexp) - 1
    e_p = 1 << (nexp - 1)
    sgnr_mask = 1 << (nexp + 2 * nman - 1)
    sgni_mask = sgnr_mask >> nman
    e_zero = -nman

    exponents = []
    raw = []
    maxbit = -e_p
    for word in words[:nfft]:
        vi = (word >> (nexp + nman)) & iq_mask
        vq = (word >> nexp) & iq_mask
        exponent = word & e_mask
        if exponent >= e_p:
            exponent -= e_p << 1
        x = vi | vq
        autoscaled_exponent = exponent
        if x:
            autoscaled_exponent += x.bit_length() - 1
            maxbit = max(maxbit, autoscaled_exponent)
        exponents.append(exponent)
        if word & sgnr_mask:
            vi |= sign_marker
        if word & sgni_mask:
            vq |= sign_marker
        raw.extend((vi, vq))

    shift = nbits - maxbit
    out = []
    for idx, value in enumerate(raw):
        exponent = exponents[idx >> 1] + shift
        sign = 1
        if value & sign_marker:
            sign = -1
            value &= ~sign_marker
        if exponent < e_zero:
            value = 0
        elif exponent < 0:
            value >>= -exponent
        else:
            value <<= exponent
        out.append(sign * value)
    return out


def _unpack_int16_words(words):
    packed = struct.pack(f"<{len(words)}I", *words)
    return list(struct.unpack(f"<{len(words) * 2}h", packed))


def unpack_csi_words(words, chip, nfft):
    chip = chip.lower()
    if chip in ("4339", "43455c0"):
        values = _unpack_int16_words(words[:nfft])
    elif chip == "4358":
        values = _unpack_float_acphy(0, nfft, words)
    elif chip == "4366c0":
        values = _unpack_float_acphy(1, nfft, words)
    else:
        raise ValueError(f"Unsupported chip: {chip}")
    return [complex(values[i], values[i + 1]) for i in range(0, len(values), 2)]


def extract_csi(filename, *, chip="4366c0", bw=80):
    nfft = _nfft_from_bw(bw)
    valid_indexes = _valid_subcarrier_indexes(bw)
    csi = []
    seq_num = []
    core_num = []

    for frame in iter_pcap_frames(filename):
        if frame["orig_len"] - (16 - 1) * 4 != nfft * 4:
            continue
        words = _payload_words(frame["payload"])
        if len(words) < 15 + nfft:
            continue

        packet_info = f"{words[13]:08X}"
        seq_num.append(packet_info[4:])
        core_num.append(packet_info[:2])

        unpacked = unpack_csi_words(words[15 : 15 + nfft], chip, nfft)
        csi.append([unpacked[idx] for idx in valid_indexes])

    if not csi:
        raise ValueError("No Nexmon CSI frames were found in the pcap.")
    return csi, seq_num, core_num


def _pad8(data):
    return data + (b"\x00" * ((8 - len(data) % 8) % 8))


def _element(data_type, data):
    return struct.pack("<II", data_type, len(data)) + _pad8(data)


def _matrix(name, flags, dims, elements):
    body = [
        _element(MI_UINT32, struct.pack("<II", flags, 0)),
        _element(MI_INT32, struct.pack(f"<{len(dims)}i", *dims)),
        _element(MI_INT8, name.encode("ascii")),
        *elements,
    ]
    payload = b"".join(body)
    return _element(MI_MATRIX, payload)


def _complex_matrix(name, rows):
    nrows = len(rows)
    ncols = len(rows[0]) if rows else 0
    real_values = []
    imag_values = []
    for col in range(ncols):
        for row in range(nrows):
            value = rows[row][col]
            real_values.append(float(value.real))
            imag_values.append(float(value.imag))
    real_data = struct.pack(f"<{len(real_values)}d", *real_values)
    imag_data = struct.pack(f"<{len(imag_values)}d", *imag_values)
    return _matrix(
        name,
        MX_DOUBLE_CLASS | MX_COMPLEX,
        [nrows, ncols],
        [_element(MI_DOUBLE, real_data), _element(MI_DOUBLE, imag_data)],
    )


def _char_matrix(name, values):
    width = max((len(value) for value in values), default=0)
    rows = len(values)
    chars = []
    for col in range(width):
        for row in range(rows):
            value = values[row]
            chars.append(ord(value[col]) if col < len(value) else 32)
    data = struct.pack(f"<{len(chars)}H", *chars) if chars else b""
    return _matrix(name, MX_CHAR_CLASS, [rows, width], [_element(MI_UINT16, data)])


def save_mat(filename, *, csi, seq_num, core_num):
    text = b"MATLAB 5.0 MAT-file, Created by tfdiff.nexmon_csi_mat"
    header = text.ljust(116, b" ") + (b"\x00" * 8) + struct.pack("<H2s", 0x0100, b"IM")
    content = b"".join(
        (
            _complex_matrix("csi", csi),
            _char_matrix("seq_num", seq_num),
            _char_matrix("core_num", core_num),
        )
    )
    output = Path(filename)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + content)
    return output


def convert_pcap_to_mat(input_file, output_file=None, *, chip="4366c0", bw=80):
    input_path = Path(input_file)
    if not input_path.is_file():
        raise FileNotFoundError(
            f"Input capture not found: {input_path}. "
            "Put the .pcap file there or pass the full path to your capture."
        )
    if output_file is None:
        output_file = input_path.with_suffix(".mat")
    csi, seq_num, core_num = extract_csi(input_path, chip=chip, bw=bw)
    return save_mat(output_file, csi=csi, seq_num=seq_num, core_num=core_num), len(csi), len(csi[0])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert Nexmon CSI .pcap files to .mat.")
    parser.add_argument("input", help="Input Nexmon CSI .pcap file.")
    parser.add_argument("output", nargs="?", help="Output .mat file. Defaults next to input.")
    parser.add_argument("--chip", default="4366c0", help="4339, 4358, 43455c0, or 4366c0.")
    parser.add_argument("--bw", default=80, type=int, help="Bandwidth in MHz: 20 or 80.")
    args = parser.parse_args(argv)

    output, packets, subcarriers = convert_pcap_to_mat(
        args.input, args.output, chip=args.chip, bw=args.bw
    )
    print(f"Saved: {output}")
    print(f"csi shape: [{packets} x {subcarriers}]")


if __name__ == "__main__":
    main()
