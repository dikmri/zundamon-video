from zvideo.reading import apply_reading


def test_longest_entry_wins():
    d = {"MiniMax": "ミニマックス", "H3": "エイチスリー", "MiniMax H3": "ミニマックス・エイチスリー"}
    assert apply_reading("MiniMax H3とMiniMax", d) == "ミニマックス・エイチスリーとミニマックス"


def test_replaced_text_is_not_replaced_again():
    d = {"A": "エー", "エー": "えー"}
    assert apply_reading("AとB", d) == "エーとB"


def test_empty_dictionary_keeps_text():
    assert apply_reading("そのままなのだ", {}) == "そのままなのだ"
