"""
Utilities for converting FLUID format Job IDs (see Flux RFC 19)
"""

from enum import Enum

from .mnemonicode import mnencode, mndecode

__all__ = ["fluid_encode", "fluid_decode", "FLUIDEncoding", "BASE58", "HEX", "DOTHEX", "WORDS", "DECIMAL",]


class FLUIDParseError(RuntimeError):
    def __init__(self, msg: str):
        super().__init__(msg)


class FLUIDEncoding(Enum):
    BASE58 = 0
    HEX = 1
    DOTHEX = 2
    WORDS = 3
    DECIMAL = 4


BASE58 = FLUIDEncoding.BASE58
HEX = FLUIDEncoding.HEX
DOTHEX = FLUIDEncoding.DOTHEX
WORDS = FLUIDEncoding.WORDS
DECIMAL = FLUIDEncoding.DECIMAL


BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def base58encode(id: int) -> str:
    """Encode an integer into a Base58 string

    Args:
        id (int): Integer to encode

    Returns:
        str: Encoded string
    """
    encoded_chars = []
    while id > 0:
        id, rem = divmod(id, 58)
        encoded_chars.append(BASE58_ALPHABET[rem])
    return ''.join(reversed(encoded_chars))


def base58decode(s: str) -> int:
    """Decode a Base58 string into an integer

    Args:
        s (str): Encoded string

    Returns:
        int: Computed integer representation
    """
    if s.startswith('f') or s.startswith('ƒ'):
        s = s[1:]
    id = 0
    mult = 1
    for c in s[::-1]:
        id += BASE58_ALPHABET.index(c) * mult
        mult *= 58
    return id


def _guess_encoding(s: str) -> FLUIDEncoding:
    """Determine the FLUID representation type

    Args:
        s (str): Encoded FLUID

    Returns:
        FLUIDEncoding: Type of encoding for `s`
    """
    if '.' in s:
        return FLUIDEncoding.DOTHEX
    elif '-' in s:
        return FLUIDEncoding.WORDS
    elif s.startswith('f') or s.startswith('ƒ'):
        return FLUIDEncoding.BASE58
    elif s.startswith('0x'):
        return FLUIDEncoding.HEX
    else:
        return FLUIDEncoding.DECIMAL


def fluid_encode(id: int, encoding: FLUIDEncoding = FLUIDEncoding.BASE58):
    if encoding == FLUIDEncoding.BASE58:
        return 'ƒ' + base58encode(id)
    elif encoding == FLUIDEncoding.HEX:
        return f'0x{id:x}'
    elif encoding == FLUIDEncoding.DOTHEX:
        sections = [0, 0, 0, 0]
        for i in range(4):
            id, sections[3 - i] = divmod(id, 65536)
        return '.'.join(f'{s:0>4x}' for s in sections)
    elif encoding == FLUIDEncoding.WORDS:
        return '--'.join('-'.join(t for t in tup) for tup in mnencode(id.to_bytes(8, 'little')))
    elif encoding == FLUIDEncoding.DECIMAL:
        return f'{id}'


def fluid_decode(s: str):
    encoding = _guess_encoding(s)
    if encoding == FLUIDEncoding.BASE58:
        return base58decode(s)
    elif encoding == FLUIDEncoding.HEX:
        return int(s[2:], 16)
    elif encoding == FLUIDEncoding.DOTHEX:
        id = 0
        mult = 1 << 64
        for dword in s.split('.'):
            mult = mult >> 16
            id += mult * int(dword, 16)
        return id
    elif encoding == FLUIDEncoding.WORDS:
        return int.from_bytes(mndecode(tuple(g.split('-', 2))
                              if '-' in g else tuple([g]) for g in s.split('--')), 'little')
    elif encoding == FLUIDEncoding.DECIMAL:
        return int(s)
    else:
        raise FLUIDParseError(f"Cannot parse {s} as a FLUID")
