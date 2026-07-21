#!/usr/bin/env python3
"""Train published SenseFi UT-HAR architectures on HAR-1 CSI amplitude."""

import argparse
import csv
import json
import random
from pathlib import Path

import h5py
import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score, recall_score
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, Dataset


class H5Dataset(Dataset):
    def __init__(self, path, indices, low, high):
        self.path, self.indices = str(path), np.asarray(indices)
        self.low, self.scale, self.handle = low, max(high - low, 1e-8), None

    def __len__(self): return len(self.indices)

    def __getitem__(self, item):
        if self.handle is None:
            self.handle = h5py.File(self.path, "r")
        x = self.handle["x"][self.indices[item]].astype(np.float32)
        x = np.clip((x - self.low) / self.scale, 0, 1)
        return torch.from_numpy(x), int(self.handle["y"][self.indices[item]])


class SenseFiLeNet(nn.Module):
    """Official SenseFi UT_HAR_LeNet, with a configurable class count."""
    def __init__(self, classes=20):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(1, 32, 7, stride=(3, 1)), nn.ReLU(True), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, (5, 4), stride=(2, 2), padding=(1, 0)),
            nn.ReLU(True), nn.MaxPool2d(2),
            nn.Conv2d(64, 96, (3, 3), stride=1), nn.ReLU(True), nn.MaxPool2d(2),
        )
        self.fc = nn.Sequential(
            nn.Linear(96 * 4 * 4, 128), nn.ReLU(), nn.Linear(128, classes)
        )

    def forward(self, x):
        x = self.encoder(x)
        return self.fc(x.view(-1, 96 * 4 * 4))


class Block(nn.Module):
    def __init__(self, cin, cout, stride=1):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(cin, cout, 3, 1, 1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(),
                                 nn.Conv2d(cout, cout, 3, stride, 1, bias=False), nn.BatchNorm2d(cout))
        self.skip = nn.Identity() if stride == 1 and cin == cout else nn.Sequential(nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))
        self.relu = nn.ReLU()

    def forward(self, x): return self.relu(self.net(x) + self.skip(x))


class SenseFiResNet18(nn.Module):
    """Official SenseFi UT_HAR_ResNet18, with a configurable class count."""
    def __init__(self, classes=20):
        super().__init__()
        self.reshape = nn.Sequential(
            nn.Conv2d(1, 3, 7, stride=(3, 1)), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(3, 3, kernel_size=(10, 11), stride=1), nn.ReLU(),
        )
        self.stem = nn.Sequential(nn.Conv2d(3, 64, 7, 2, 3, bias=False), nn.BatchNorm2d(64), nn.ReLU(), nn.MaxPool2d(3, 2, 1))
        layers, cin = [], 64
        for cout, stride in [(64, 1), (128, 2), (256, 2), (512, 2)]:
            layers += [Block(cin, cout, stride), Block(cout, cout)]
            cin = cout
        self.layers = nn.Sequential(*layers)
        self.head = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(512, classes))

    def forward(self, x): return self.head(self.layers(self.stem(self.reshape(x))))


def split_indices(labels, participants, split, test_participant, seed):
    all_idx = np.arange(len(labels))
    if split == "participant":
        test = all_idx[participants == test_participant]
        rest = all_idx[participants != test_participant]
        train, val = train_test_split(rest, test_size=.1, random_state=seed, stratify=labels[rest])
    else:
        train, temp = train_test_split(all_idx, test_size=.3, random_state=seed, stratify=labels)
        val, test = train_test_split(temp, test_size=.5, random_state=seed, stratify=labels[temp])
    return train, val, test


def minmax(path, indices, chunk=256):
    low, high = np.inf, -np.inf
    with h5py.File(path, "r") as f:
        for begin in range(0, len(indices), chunk):
            for idx in indices[begin:begin + chunk]:
                a = f["x"][idx]
                low, high = min(low, float(a.min())), max(high, float(a.max()))
    return low, high


def evaluate(model, loader, device):
    model.eval(); true, pred = [], []
    with torch.no_grad():
        for x, y in loader:
            true.extend(y.numpy()); pred.extend(model(x.to(device)).argmax(1).cpu().numpy())
    return dict(accuracy=accuracy_score(true, pred), macro_f1=f1_score(true, pred, average="macro", zero_division=0),
                macro_recall=recall_score(true, pred, average="macro", zero_division=0))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True); p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--model", choices=["lenet", "resnet18"], default="lenet")
    p.add_argument("--split", choices=["random-window", "participant"], default="random-window")
    p.add_argument("--test-participant", type=int); p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--batch-size", type=int, default=64); p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--patience", type=int, default=8); p.add_argument("--seed", type=int, default=111)
    args = p.parse_args()
    if args.split == "participant" and args.test_participant is None: p.error("participant split requires --test-participant")
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    with h5py.File(args.data, "r") as f:
        labels, participants = f["y"][:], f["participant"][:]
    train, val, test = split_indices(labels, participants, args.split, args.test_participant, args.seed)
    low, high = minmax(args.data, train)
    loaders = {name: DataLoader(H5Dataset(args.data, idx, low, high), batch_size=args.batch_size,
                                shuffle=name == "train", num_workers=2, pin_memory=True)
               for name, idx in [("train", train), ("val", val), ("test", test)]}
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = (SenseFiLeNet() if args.model == "lenet" else SenseFiResNet18()).to(device)
    optimizer, criterion = torch.optim.Adam(model.parameters(), lr=args.lr), nn.CrossEntropyLoss()
    args.output_dir.mkdir(parents=True, exist_ok=True); best, stale, history = -1, 0, []
    for epoch in range(1, args.epochs + 1):
        model.train(); losses = []
        for x, y in loaders["train"]:
            optimizer.zero_grad(); loss = criterion(model(x.to(device)), y.to(device)); loss.backward(); optimizer.step(); losses.append(loss.item())
        val_metrics = evaluate(model, loaders["val"], device)
        history.append({"epoch": epoch, "loss": float(np.mean(losses)), **{f"val_{k}": v for k, v in val_metrics.items()}})
        print(history[-1])
        if val_metrics["accuracy"] > best:
            best, stale = val_metrics["accuracy"], 0; torch.save(model.state_dict(), args.output_dir / "best.pt")
        else:
            stale += 1
            if stale >= args.patience: break
    model.load_state_dict(torch.load(args.output_dir / "best.pt", map_location=device))
    result = {"model": args.model, "model_source": "official SenseFi UT-HAR architecture; output 7->20",
              "split": args.split, "test_participant": args.test_participant,
              "train_samples": len(train), "validation_samples": len(val), "test_samples": len(test),
              "normalization": "train-global-minmax", "seed": args.seed, **evaluate(model, loaders["test"], device)}
    with open(args.output_dir / "history.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=history[0]); writer.writeheader(); writer.writerows(history)
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
