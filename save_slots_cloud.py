import requests
import json

GAS_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbwnJXm6B3ZrS0jp5dsoKV6n3ghCOOtjxcSzAVtVlZ3nCk6MwZIKgMVV6e7FJcdM0PaZ4A/exec"

slots = [
    {
        "id": 1,
        "name": "나스닥100 동적 계단식",
        "memo": "평시 SCHD 60:QQQ 40 유지, 나스닥 -15%/-25%/-40%/-60%/-80% 계단식 대응",
        "benchmark": "^NDX",
        "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
        "dropStages": [
            {"threshold": -15.0, "weights": {"SCHD": 0.40, "QQQ": 0.60}, "name": "1차 하락 (-15%)"},
            {"threshold": -25.0, "weights": {"SCHD": 0.40, "QQQ": 0.40, "QLD": 0.20}, "name": "2차 하락 (-25%)"},
            {"threshold": -40.0, "weights": {"SCHD": 0.20, "QQQ": 0.40, "QLD": 0.40}, "name": "3차 하락 (-40%)"},
            {"threshold": -60.0, "weights": {"SCHD": 0.20, "QQQ": 0.20, "QLD": 0.40, "TQQQ": 0.20}, "name": "4차 하락 (-60%)"},
            {"threshold": -80.0, "weights": {"SCHD": 0.00, "QQQ": 0.20, "QLD": 0.40, "TQQQ": 0.40}, "name": "5차 하락 (-80%)"}
        ],
        "gainThresholdPct": 20.0,
        "baseRecoveryPct": 0.0,
        "feeRate": 0.15
    },
    {
        "id": 2,
        "name": "레버리지 조기투입",
        "memo": "평시 SCHD 60:QQQ 40 유지, 나스닥 -10%부터 QLD 20% 조기 투입 및 -40%까지 QLD 80% 안전 공략",
        "benchmark": "^NDX",
        "baseWeights": {"SCHD": 0.60, "QQQ": 0.40},
        "dropStages": [
            {"threshold": -10.0, "weights": {"SCHD": 0.40, "QQQ": 0.40, "QLD": 0.20}, "name": "1차 하락 (-10%)"},
            {"threshold": -25.0, "weights": {"SCHD": 0.20, "QQQ": 0.40, "QLD": 0.40}, "name": "2차 하락 (-25%)"},
            {"threshold": -40.0, "weights": {"SCHD": 0.20, "QQQ": 0.00, "QLD": 0.80}, "name": "3차 하락 (-40%)"},
            {"threshold": -60.0, "weights": {"SCHD": 0.20, "QQQ": 0.00, "QLD": 0.40, "TQQQ": 0.40}, "name": "4차 하락 (-60%)"},
            {"threshold": -80.0, "weights": {"SCHD": 0.20, "QQQ": 0.00, "QLD": 0.00, "TQQQ": 0.80}, "name": "5차 하락 (-80%)"}
        ],
        "gainThresholdPct": 20.0,
        "baseRecoveryPct": 0.0,
        "feeRate": 0.15
    }
]

for i in range(3, 11):
    slots.append({
        "id": i,
        "name": f"전략 {i}",
        "memo": "",
        "benchmark": "^NDX",
        "baseWeights": {"QQQ": 0.60, "SCHD": 0.40},
        "dropStages": [
            {"threshold": -20.0, "weights": {"QQQ": 0.40, "QLD": 0.30, "SCHD": 0.30}, "name": "1차 하락 (-20%)"}
        ],
        "gainThresholdPct": 20.0,
        "baseRecoveryPct": 0.0,
        "feeRate": 0.15
    })

payload = {
    "action": "save_strategy_slots",
    "slots": slots,
    "activeSlotId": 2
}

resp = requests.post(GAS_WEBAPP_URL, json=payload, timeout=15)
print("GAS Response:", resp.text)
