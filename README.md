# BFI to Widar Input

This workspace prepares decoded BFI packet data so a CSI-based Widar model can
measure classification accuracy with BFI-derived inputs.

Important limitation: BFI is compressed feedback derived from the wireless
channel. It is not a full raw CSI capture, so this converter does not claim to
recover original CSI. It reshapes BFI into the same time-major feature interface
that Widar CSI loaders commonly expect.

## CSI Extraction

CSI traces are extracted from Nexmon PCAP files using the MATLAB files copied
from `kfoysalhaque/CSI-BFI-HAR`:

```text
CSI-Extraction/Extract_CSI.m
```

If MATLAB is not installed or `matlab` is not on your `PATH`, use the included
pure-Python converter instead:

```bash
python3 -m tfdiff.nexmon_csi_mat CSI-Samples/D_1_M1_P2_short.pcap --chip 4366c0 --bw 80
```

That command writes `CSI-Samples/D_1_M1_P2_short.mat`.

### Prerequisites

- MATLAB, or GNU Octave with compatible MEX support
- Files in `CSI-Extraction/`:
  - `Extract_CSI.m`
  - `readpcap.m`
  - `plotcsi.m` for optional visualization
  - `unpack_float.mexa64` for Broadcom float unpacking

On macOS or any platform where `unpack_float.mexa64` is not usable, compile the
MEX helper from inside `CSI-Extraction/`:

```matlab
mex unpack_float.c
```

### Input

A Nexmon CSI capture file, for example:

```text
D_1_M1_P2_short.pcap
```

Place your `.pcap` file anywhere convenient, for example under `CSI-Samples/`.
You can pass the file path directly when running `Extract_CSI`:

```matlab
Extract_CSI('../CSI-Samples/D_1_M1_P2_short.pcap')
```

### Configuration

Pass the chip and bandwidth as optional arguments:

```matlab
Extract_CSI('../CSI-Samples/D_1_M1_P2_short.pcap', '4366c0', 80)
```

- `CHIP`: for example `4366c0`
- `BW`: bandwidth in MHz, for example `80`

For `BW = 80`, the script keeps valid data subcarriers and removes null/pilot
bins, producing 242 CSI subcarriers per packet.

### Run

From the repository root:

```bash
cd CSI-Extraction
matlab -batch "Extract_CSI('../CSI-Samples/D_1_M1_P2_short.pcap', '4366c0', 80)"
```

Or run `Extract_CSI.m` directly from the MATLAB editor while your current folder
is `CSI-Extraction`.

To choose an explicit output path:

```bash
cd CSI-Extraction
matlab -batch "Extract_CSI('../CSI-Samples/D_1_M1_P2_short.pcap', '4366c0', 80, '../CSI-Samples/D_1_M1_P2_short.mat')"
```

### Output

The script saves a `.mat` file next to the input PCAP, with the same base
filename:

```text
Input:  ../CSI-Samples/D_1_M1_P2_short.pcap
Output: ../CSI-Samples/D_1_M1_P2_short.mat
```

Saved variables:

- `csi`: complex CSI matrix of size `[num_packets x num_subcarriers]`, with 242
  subcarriers for 80 MHz
- `seq_num`: sequence identifier extracted per packet
- `core_num`: RF core identifier extracted per packet

## Output Format

The converter writes `.mat` files named like `user000000.mat` with:

- `feature`: BFI-derived feature sequence shaped `[packet_time, feature_dim]`
- `cond`: activity/gesture label or condition vector

By default, all non-time BFI dimensions such as RX, TX, subcarrier, angle, or
codebook dimensions are flattened into one feature dimension.

## Convert BFI Packets

If the BFI is still inside an 802.11 packet capture, extract the VHT compressed
beamforming reports first:

```bash
python -m tfdiff.bfi_pcapng A_1_M1_P2.pcapng A_1_M1_P2_bfi.npz --label 1 --mode bytes
```

The extractor currently targets VHT action frames with category `0x15` and
action code `0x00`, which are used for compressed beamforming feedback. It saves:

- `feature`: `[packet_time, padded_bfi_report_bytes]`
- `cond`: class label
- `mimo_control`: raw VHT MIMO control value per packet
- `packet_index`: source packet index in the capture

Use `--mode bits` if you want bit-level feedback features instead of byte-level
features.

Convert a directory of decoded BFI packet files:

```bash
python -m tfdiff.bfi_widar /path/to/bfi_packets /path/to/widar_input --time-axis 0
```

Convert one file:

```bash
python -m tfdiff.bfi_widar packet.mat user000000.mat --data-key bfi --cond-key label
```

Input files can be `.mat` or `.npz`. The converter looks for BFI data under
keys such as `bfi`, `beamforming_feedback`, `feedback`, `csi`, or `feature`.
Labels are read from keys such as `cond`, `label`, `gesture`, or `activity`.

## Feature Modes

Use `--feature-mode` to match the Widar model input preprocessing:

```bash
python -m tfdiff.bfi_widar packets widar_input --feature-mode complex
python -m tfdiff.bfi_widar packets widar_input --feature-mode real
python -m tfdiff.bfi_widar packets widar_input --feature-mode amp_phase
```

- `complex`: complex array if available; real BFI becomes complex with zero imaginary part
- `real`: float feature values; complex values become real/imag pairs
- `amp_phase`: complex values become amplitude/phase pairs

Use `--keep-shape` only if your Widar implementation expects the original BFI
tensor layout instead of flattened `[packet_time, feature_dim]` samples.

## Local Loader Note

The included `tfdiff.dataset.WiFiDataset` reads `user*.mat` files with
`feature` and `cond` keys. That can be used as a quick compatibility check, but
the conversion target is the Widar CSI accuracy pipeline, not RF-Diffusion
training.
