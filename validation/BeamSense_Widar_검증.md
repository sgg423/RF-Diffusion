# BeamSense BFI 검증 및 Widar 3.0 적용 가능성 분석

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

1. 단일 링크 CSI tensor용 CNN baseline 구축
2. CSI와 BFA에 동일한 공통 CNN backbone을 적용한 통제 비교
3. CSI와 BFA tensor를 각각 RF-Diffusion으로 증강
4. 실제 데이터만 사용한 경우와 합성 데이터를 추가한 경우의 정확도 비교
5. 저데이터 및 participant-holdout 조건에서 증강 효과 분석

비교 실험에서는 데이터 split, CNN 학습 조건, epoch, optimizer, random seed와 합성 데이터 비율을 동일하게 유지해야 한다.
