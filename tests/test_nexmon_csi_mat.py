import struct

from tfdiff.nexmon_csi_mat import (
    convert_pcap_to_mat,
    convert_path_to_rf_diffusion_windows,
    convert_pcap_to_rf_diffusion_windows,
    extract_csi,
)


def _classic_pcap(payload, orig_len=None):
    if orig_len is None:
        orig_len = len(payload)
    global_header = (
        b"\xd4\xc3\xb2\xa1"
        + struct.pack("<HHIIII", 2, 4, 0, 0, 65535, 127)
    )
    packet_header = struct.pack("<IIII", 0, 0, len(payload), orig_len)
    return global_header + packet_header + payload


def _classic_pcap_many(payloads, orig_len):
    global_header = (
        b"\xd4\xc3\xb2\xa1"
        + struct.pack("<HHIIII", 2, 4, 0, 0, 65535, 127)
    )
    packets = []
    for payload in payloads:
        packets.append(struct.pack("<IIII", 0, 0, len(payload), orig_len) + payload)
    return global_header + b"".join(packets)


def _iq_word(real, imag):
    return struct.unpack("<I", struct.pack("<hh", real, imag))[0]


def test_extract_nexmon_csi_from_classic_pcap_int16(tmp_path):
    nfft = 64
    words = [0] * 15
    words[13] = 0xABCD1234
    words.extend(_iq_word(i, -i) for i in range(nfft))
    payload = struct.pack(f"<{len(words)}I", *words)
    pcap = tmp_path / "sample.pcap"
    pcap.write_bytes(_classic_pcap(payload, orig_len=nfft * 4 + 60))

    csi, seq_num, core_num = extract_csi(pcap, chip="4339", bw=20)

    assert len(csi) == 1
    assert len(csi[0]) == 56
    assert csi[0][0] == complex(4, -4)
    assert csi[0][-1] == complex(60, -60)
    assert seq_num == ["1234"]
    assert core_num == ["AB"]


def test_convert_nexmon_csi_to_mat_file(tmp_path):
    nfft = 64
    words = [0] * 15
    words[13] = 0x01020003
    words.extend(_iq_word(i, i + 1) for i in range(nfft))
    pcap = tmp_path / "sample.pcap"
    mat = tmp_path / "sample.mat"
    pcap.write_bytes(_classic_pcap(struct.pack(f"<{len(words)}I", *words), nfft * 4 + 60))

    output, packets, subcarriers = convert_pcap_to_mat(pcap, mat, chip="4339", bw=20)

    assert output == mat
    assert packets == 1
    assert subcarriers == 56
    assert mat.read_bytes().startswith(b"MATLAB 5.0 MAT-file")


def test_convert_nexmon_csi_to_rf_diffusion_windows(tmp_path):
    nfft = 64
    words = [0] * 15
    words[13] = 0x01020003
    words.extend(_iq_word(i, i + 1) for i in range(nfft))
    packet = struct.pack(f"<{len(words)}I", *words)
    pcap = tmp_path / "A_1_M1_P1.pcap"
    pcap.write_bytes(_classic_pcap_many([packet, packet, packet], nfft * 4 + 60))

    output_dir = tmp_path / "rf"
    outputs, packets, subcarriers, label = convert_pcap_to_rf_diffusion_windows(
        pcap,
        output_dir,
        chip="4339",
        bw=20,
        window_size=2,
        stride=1,
    )

    assert packets == 3
    assert subcarriers == 56
    assert label == 1
    assert [path.name for path in outputs] == ["user000000.mat", "user000001.mat"]
    assert outputs[0].read_bytes().startswith(b"MATLAB 5.0 MAT-file")


def test_convert_nexmon_csi_directory_to_rf_diffusion_windows(tmp_path):
    nfft = 64
    words = [0] * 15
    words[13] = 0x01020003
    words.extend(_iq_word(i, i + 1) for i in range(nfft))
    packet = struct.pack(f"<{len(words)}I", *words)
    for name in ("A_1_M1_P1.pcap", "B_1_M1_P1.pcap"):
        (tmp_path / name).write_bytes(_classic_pcap_many([packet, packet], nfft * 4 + 60))

    output_dir = tmp_path / "rf"
    outputs, summaries = convert_path_to_rf_diffusion_windows(
        tmp_path,
        output_dir,
        chip="4339",
        bw=20,
        window_size=2,
        stride=2,
    )

    assert [path.name for path in outputs] == ["user000000.mat", "user000001.mat"]
    assert [summary["label"] for summary in summaries] == [1, 2]
    assert [summary["windows"] for summary in summaries] == [1, 1]
