from src.shared.peer_prompt import format_peer_block


def _print_case(name: str, result: str) -> None:
    print(f"\n--- {name} ---\n{result}")


def test_female_same_age_bans_bro_terms():
    result = format_peer_block(
        peer_nickname="小夏",
        peer_user_id=10,
        peer_age_band="25-30",
        peer_gender="female",
        peer_mbti="INFJ",
        host_age_band="25-30",
    )
    _print_case("female_same_age", result)

    assert "禁用" in result
    assert "哥们儿" in result
    assert "可以用'哥们儿" not in result


def test_male_same_age_allows_bro_terms():
    result = format_peer_block(
        peer_nickname="阿树",
        peer_user_id=11,
        peer_age_band="25-30",
        peer_gender="male",
        peer_mbti="ENFP",
        host_age_band="25-30",
    )
    _print_case("male_same_age", result)

    assert "可以用'哥们儿" in result
    assert "禁用" not in result


def test_male_large_age_gap_does_not_allow_bro_terms():
    result = format_peer_block(
        peer_nickname="老周",
        peer_user_id=12,
        peer_age_band="40+",
        peer_gender="male",
        peer_mbti="INTP",
        host_age_band="18-25",
    )
    _print_case("male_large_age_gap", result)

    assert "跨年龄段" in result
    assert "可以用'哥们儿" not in result


def test_non_binary_uses_neutral_addressing_only():
    result = format_peer_block(
        peer_nickname="青禾",
        peer_user_id=13,
        peer_age_band="30-35",
        peer_gender="non_binary",
        peer_mbti="ISFP",
        host_age_band="30-35",
    )
    _print_case("non_binary", result)

    assert "@青禾" in result
    assert "TA" in result
    assert "带性别预设" in result
    assert "可以用'哥们儿" not in result
    assert "可以用'姐妹" not in result


def test_prefer_not_to_say_defaults_to_nickname():
    result = format_peer_block(
        peer_nickname="隐山",
        peer_user_id=14,
        peer_age_band="30-35",
        peer_gender="prefer_not_to_say",
        peer_mbti=None,
        host_age_band="30-35",
    )
    _print_case("prefer_not_to_say", result)

    assert "未透露性别" in result
    assert "默认 @隐山" in result


def test_all_null_fields_warns_and_falls_back_to_neutral_addressing():
    result = format_peer_block(
        peer_nickname=None,
        peer_user_id=None,
        peer_age_band=None,
        peer_gender=None,
        peer_mbti=None,
        host_age_band=None,
    )
    _print_case("all_null", result)

    assert "NULL 字段多" in result
    assert "(对方资料不全)" in result


def test_missing_nickname_uses_user_id_placeholder():
    result = format_peer_block(
        peer_nickname=None,
        peer_user_id=42,
        peer_age_band="25-30",
        peer_gender="female",
        peer_mbti="ENFJ",
        host_age_band="25-30",
    )
    _print_case("missing_nickname", result)

    assert "user_42" in result


def test_none_mbti_does_not_render_mbti_line():
    result = format_peer_block(
        peer_nickname="无型",
        peer_user_id=43,
        peer_age_band="25-30",
        peer_gender="male",
        peer_mbti=None,
        host_age_band="25-30",
    )
    _print_case("none_mbti", result)

    assert "MBTI:" not in result


def test_age_gap_boundary_two_bands_is_large_one_band_is_not():
    two_band_gap = format_peer_block(
        peer_nickname="远龄",
        peer_user_id=44,
        peer_age_band="30-35",
        peer_gender="male",
        peer_mbti=None,
        host_age_band="18-25",
    )
    one_band_gap = format_peer_block(
        peer_nickname="近龄",
        peer_user_id=45,
        peer_age_band="30-35",
        peer_gender="male",
        peer_mbti=None,
        host_age_band="25-30",
    )
    _print_case("two_band_gap", two_band_gap)
    _print_case("one_band_gap", one_band_gap)

    assert "跨年龄段" in two_band_gap
    assert "可以用'哥们儿" not in two_band_gap
    assert "跨年龄段" not in one_band_gap
    assert "可以用'哥们儿" in one_band_gap
