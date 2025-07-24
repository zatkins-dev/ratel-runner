import pytest
from ratel_runner.helper.flux.fluid import *

TEST_ID = 6731191091817518


def test_base58():
    expected = 'ƒuZZybuNNy'
    expected_alt = 'fuZZybuNNy'
    assert fluid_encode(TEST_ID, BASE58) == expected
    assert fluid_decode(expected) == TEST_ID
    assert fluid_decode(expected_alt) == TEST_ID


def test_dothex():
    expected = '0017.e9fb.8df1.6c2e'
    assert fluid_encode(TEST_ID, DOTHEX) == expected
    assert fluid_decode(expected) == TEST_ID


def test_hex():
    expected = '0x17e9fb8df16c2e'
    assert fluid_encode(TEST_ID, HEX) == expected
    assert fluid_decode(expected) == TEST_ID


def test_words():
    expected = 'reform-remote-galileo--heart-package-academy'
    assert fluid_encode(TEST_ID, WORDS) == expected
    assert fluid_decode(expected) == TEST_ID


def test_decimal():
    expected = '6731191091817518'
    assert fluid_encode(TEST_ID, DECIMAL) == expected
    assert fluid_decode(expected) == TEST_ID
