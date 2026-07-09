import struct

from tfdiff.nexmon_csi_mat import convert_pcap_to_mat, extract_csi


def _classic_pcap(payload, orig_len=None):
    if orig_len is None:
        orig_len = len(payload)
    global_header = (
        b"\xd4\xc3\xb2\xa1"
        + struct.pack("<HHIIII", 2, 4, 0, 0, 65535, 127)
    )
    packet_header = struct.pack("<IIII", 0, 0, len(payload), orig_len)
    return global_header + packet_header + payload


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
