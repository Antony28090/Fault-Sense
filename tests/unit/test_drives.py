import pytest

from faultsense.drives import named_drive_models


@pytest.mark.parametrize("text, expected", [
    ("OHF on an ATV61", ["ATV61"]),
    ("atv 71 shows USF", ["ATV71"]),
    ("Our ATV-312 with a remote keypad", ["ATV312"]),
    ("ATV630D11N4 trips on OCF", ["ATV630"]),
    ("ATV12H075M2 fan drive", ["ATV12"]),
    ("ATV6B0 and ATV9A0 cabinets", ["ATV6B0", "ATV9A0"]),
    ("Altivar 71 overheating", ["ATV71"]),
    ("Altivar Process 930 on the hoist", ["ATV930"]),
    ("ATS48 soft starter USF", ["ATS48"]),
    ("Altistart 22 shows a fault", ["ATS22"]),
    ("replaced the ATV61 with an ATV630", ["ATV61", "ATV630"]),
    ("ATV630 and atv630 again", ["ATV630"]),
    ("Pump trips on hot afternoons", []),
    ("OHF on the pump, 630 rpm", []),
])
def test_named_drive_models(text, expected):
    assert named_drive_models(text) == expected
