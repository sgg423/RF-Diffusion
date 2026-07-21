# CSI/BFI 센싱 기준 성능 및 적용 가능성 검증

## 1. 검증 목적

CSI-BFI-HAR Dataset의 HAR-1 데이터를 이용해 다음 항목을 확인하였다.

1. BFI에서 추출한 Beamforming Feedback Angle(BFA) tensor가 행동 센싱에 사용될 수 있는지 검증
2. 공개된 BeamSense CNN 구조를 HAR-1 BFI에 적용한 분류 정확도 측정
3. HAR-1 CSI를 원본 Widar 3.0의 BVP로 변환할 수 있는지 검토

## 2. BFI 데이터와 전처리

사용한 BFI 데이터의 범위는 다음과 같다.

- 데이터셋: CSI-BFI-HAR Dataset
- 세부 경로: `HAR-1/BFI/M1`
- 날짜: Day 1
- 참여자: P1~P3
- 행동: A~T, 총 20개 클래스
- 원본 PCAPNG: 60개

BFI를 다음 과정으로 변환하였다.

```text
BFI PCAPNG
→ VHT Compressed Beamforming Report 추출
→ 9-bit φ 및 7-bit ψ 해석
→ 234개 서브캐리어의 BFA 추출
→ 연속 10개 BFI 패킷으로 window 구성
→ BFA tensor 생성
```

각 BFA tensor의 형태는 `(10, 234, 4)`이며, 네 채널은 `φ11`, `φ21`, `ψ21`, `ψ31`이다.

전체 변환 결과는 다음과 같다.

```text
BFA tensor: (40,675, 10, 234, 4)
Label:      (40,675,)
실패 파일:  0개
```

## 3. BeamSense CNN 정확도

BeamSense 공개 코드의 2D CNN 계층 구조를 사용하고 HAR-1 BFA tensor로 모델을 처음부터 재학습하였다.

### 3.1 Random-window 평가

BeamSense 공개 코드와 유사하게 개별 BFA window를 무작위로 분할하였다.

```text
Train:      70%
Validation: 15%
Test:       15%
Random seed: 111
```

| 항목 | 결과 |
|---|---:|
| Train samples | 28,529 |
| Validation samples | 6,064 |
| Test samples | 6,082 |
| Accuracy | 93.82% |
| Macro-F1 | 94.07% |
| Macro-recall | 94.13% |

이 결과를 통해 BFI에서 추출한 BFA tensor가 HAR-1의 행동을 구분할 수 있는 센싱 정보를 포함하며, BeamSense 방식의 BFI 기반 행동 센싱이 가능함을 확인하였다.

### 3.2 Participant-holdout 평가

특정 참여자의 전체 데이터를 테스트로 제외하는 participant-independent 평가에서는 정확도가 크게 낮아졌다. 예를 들어 P3를 테스트로 제외한 결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| Train samples | 25,388 |
| Validation samples | 2,809 |
| Test samples | 12,478 |
| Accuracy | 13.17% |
| Macro-F1 | 11.88% |
| Macro-recall | 12.84% |

P1과 P2 holdout에서도 낮은 성능이 확인되었다. 따라서 현재 BeamSense CNN은 동일 데이터 분포 내에서는 높은 정확도를 보이지만 미관측 참여자에 대한 일반화에는 한계가 있다.

Random-window 방식에서는 동일 PCAP의 인접 window가 train과 test에 함께 포함될 수 있으므로, 93.82%의 결과를 participant-independent 성능으로 해석해서는 안 된다.

## 4. CSI 데이터 구조 확인

HAR-1 CSI M1의 원본 추출 MAT 파일을 확인한 결과는 다음과 같다.

```text
csi:      (321,295, 242), complex128
seq_num:  (321,295,)
core_num: (321,295,)
```

`core_num`의 고유값은 다음과 같이 한 종류뿐이었다.

```text
core_num unique: ['00']
```

따라서 현재 CSI는 다음과 같은 단일 core·단일 링크 구조이다.

```text
[packet/time, subcarrier]
```

RF-Diffusion용으로 가공된 CSI MAT 파일도 다음처럼 단일 CSI stream만 보존한다.

```text
feature:         (N, 90), complex128
cond:            (1, 4)
source_filename: 원본 행동·날짜·장치·참여자 파일명
```

## 5. Widar 3.0 적용 가능성

원본 Widar 3.0의 BVP 생성에는 여러 안테나 또는 여러 링크에서 얻은 CSI를 이용한 속도 성분 추정이 필요하다. 그러나 HAR-1 CSI M1에는 하나의 core만 존재하고 다중 안테나·링크 차원이 없다.

따라서 현재 데이터에서는 다음 파이프라인을 원본 방식으로 수행하기 어렵다.

```text
HAR-1 CSI M1
→ 원본 Widar BVP
→ 원본 Widar 3.0
→ Widar 3.0 정확도
```

원본 PCAP을 다시 MAT로 추출해도 PCAP에 존재하지 않는 다중 core 또는 링크 정보가 새로 생성되지는 않는다. 기존 추출 코드가 특정 core를 필터링하지 않았다는 것을 추가로 확인하면 이 결론을 확정할 수 있다.

현재 단일 링크 CSI로 Doppler 또는 time-frequency 표현을 생성하고 CNN을 학습하는 것은 가능하지만, 이 결과는 `원본 Widar 3.0 정확도`가 아니라 다음과 같이 명시해야 한다.

- Single-link CSI CNN baseline
- CSI-based time-frequency sensing baseline
- Widar-inspired Doppler baseline

## 6. 최종 결론

### BFI

> HAR-1 BFI로부터 생성한 `(10, 234, 4)` BFA tensor를 BeamSense CNN에 적용한 결과, random-window 조건에서 93.82%의 정확도와 94.07%의 Macro-F1을 기록하였다. 이를 통해 BFI 기반 행동 센싱의 적용 가능성을 확인하였다.

### CSI와 Widar

> HAR-1 CSI M1은 단일 core CSI만 포함하여 원본 Widar 3.0 BVP 생성에 필요한 다중 안테나·링크 조건을 충족하지 못한다. 따라서 현재 데이터로 원본 Widar 3.0 정확도를 측정하는 것은 어렵고, 단일 링크 CSI를 입력으로 사용하는 별도의 CNN baseline이 필요하다.

## 7. 이후 실험 계획

1. 단일 링크 CSI tensor용 공개 SenseFi CNN baseline 구축
2. CSI와 BFA에 동일한 공통 CNN backbone을 적용한 통제 비교
3. CSI와 BFA tensor를 각각 RF-Diffusion으로 증강
4. 실제 데이터만 사용한 경우와 합성 데이터를 추가한 경우의 정확도 비교
5. 저데이터 및 participant-holdout 조건에서 증강 효과 분석

비교 실험에서는 데이터 split, CNN 학습 조건, epoch, optimizer, random seed와 합성 데이터 비율을 동일하게 유지해야 한다.

### SenseFi 기반 CSI 기준 성능

단일 링크 CSI를 입력으로 받는 공개 벤치마크 SenseFi의 UT-HAR 모델을 사용한다. UT-HAR 입력은 `(1, 250, 90)`이고 HAR-1 RF MAT의 CSI feature는 `(N, 90)`이므로, 복소 CSI의 진폭을 250패킷 단위로 분할하면 입력 규격이 일치한다.

공개 SenseFi의 LeNet 및 ResNet 구조를 유지하고 마지막 출력층만 UT-HAR의 7개 클래스에서 HAR-1의 20개 클래스로 변경한다. 이는 사전학습 모델을 그대로 평가하는 것이 아니라 검증된 공개 아키텍처를 HAR-1에 맞춰 처음부터 재학습하는 실험이다.

```bash
python scripts/har1_csi_to_sensefi.py \
  --input-dir /home/leehan/RF-Diffusion/dataset/hug_CLI/HAR-1/CSI/M1_rf_original \
  --output /home/leehan/datasets/har1_csi_sensefi_m1.h5

python scripts/train_sensefi_har1.py \
  --data /home/leehan/datasets/har1_csi_sensefi_m1.h5 \
  --output-dir /home/leehan/results/sensefi_har1_lenet_random \
  --model lenet --split random-window --epochs 50 --seed 111
```

BFI 결과와 비교할 1차 CSI 실험은 동일한 random-window 비율(70/15/15)과 seed 111을 사용한다. 일반화 성능은 별도로 `--split participant --test-participant 1`, `2`, `3`을 실행한다.

#### Random-window 공식 구조 측정 결과

BFI 실험과 동일하게 window 단위로 70/15/15 분할하고 seed 111을 사용하였다. 정규화 범위는 학습 데이터에서만 산출하였다.

| 모델 | Train | Validation | Test | Accuracy | Macro-F1 | Macro-recall |
|---|---:|---:|---:|---:|---:|---:|
| SenseFi UT-HAR LeNet | 28,876 | 6,188 | 6,188 | 93.08% | 93.07% | 93.01% |
| SenseFi UT-HAR ResNet18 | 28,876 | 6,188 | 6,188 | **96.98%** | **96.98%** | **96.98%** |

공식 SenseFi UT-HAR 계층 구조를 그대로 사용하고 출력층만 7개에서 HAR-1의 20개 클래스로 변경하여 처음부터 재학습하였다. 이를 통해 HAR-1 단일 링크 CSI 진폭에도 20개 행동을 구분할 수 있는 센싱 정보가 존재함을 확인하였다.

#### Cross-participant 측정 결과

한 참여자의 모든 window를 학습에서 제외하고 해당 참여자만 테스트하는 participant-holdout 평가를 수행하였다. 모델, 정규화와 seed는 위 ResNet18 실험과 동일하며, 정규화 범위는 각 fold의 학습 참여자에서만 계산하였다.

| Test participant | Train | Validation | Test | Accuracy | Macro-F1 | Macro-recall |
|---|---:|---:|---:|---:|---:|---:|
| P1 | 24,101 | 2,678 | 14,473 | 12.54% | 9.88% | 13.14% |
| P2 | 25,479 | 2,832 | 12,941 | 16.33% | 12.02% | 15.54% |
| P3 | 24,672 | 2,742 | 13,838 | 12.68% | 8.08% | 12.68% |
| Fold 평균 | - | - | - | **13.85%** | **9.99%** | **13.79%** |

20개 클래스의 무작위 추측 정확도는 5%이다. CSI의 in-domain 정확도는 96.98%였으나 미관측 참여자 평균은 13.85%로 83.13%p 감소하였다. 이 결과는 현재 모델이 동일 데이터 분포에서는 행동을 잘 분류하지만 참여자 변화에 매우 민감함을 보여주며, RF-Diffusion 증강 전 CSI cross-participant 기준선으로 사용한다.

### CSI·BFI 기준 성능 요약

| 데이터 | 센싱 표현 | 공개 모델 기반 분류기 | Accuracy | Macro-F1 | Macro-recall |
|---|---|---|---:|---:|---:|
| CSI | 진폭 `(1, 250, 90)` | SenseFi UT-HAR ResNet18 | 96.98% | 96.98% | 96.98% |
| BFI | BFA `(10, 234, 4)` | BeamSense CNN | 93.82% | 94.07% | 94.13% |

두 결과는 각각의 공개 모델을 이용한 독립적인 기준 성능이다. 입력 표현과 분류기가 다르므로 96.98%와 93.82%의 차이를 CSI와 BFI 자체의 우열로 해석하지 않는다.

또한 두 결과는 동일 분포의 random-window 평가이므로 센싱 가능성을 검증하는 상한 기준선으로 사용한다. 이후 연구의 핵심 목표는 이미 높은 동일 분포 정확도를 더 높이는 것이 아니라, 미관측 참여자·환경·장치 및 저데이터 조건에서 RF-Diffusion 증강이 일반화 성능과 환경 간 안정성을 개선하는지 검증하는 것이다.
