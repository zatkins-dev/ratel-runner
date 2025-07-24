from ._utils import chunk_sequence, from_base, to_base
from ._wordlist import index_to_word, word_to_index


def _block_to_indices(block):
    if len(block) > 4:
        raise ValueError("block too big")

    # `menmonicode` uses little-endian numbers.
    num = from_base(256, reversed(block))

    indices = list(reversed(to_base(1626, num)))

    # Pad the list of indices to the correct size.
    length = {
        1: 1,
        2: 2,
        3: 3,
        4: 3,
    }[len(block)]
    indices += [0] * (length - len(indices))

    # The third byte in a block slightly leaks into the third word.  A
    # different set of words is used for this case to distinguish it from the
    # four byte case.
    if len(block) == 3:
        indices[-1] += 1626

    return indices


def _block_to_words(block):
    for i in _block_to_indices(block):
        yield index_to_word(i)


def mnencode(data):
    """Encode a bytes object as an iterator of tuples of words.

    >>> list(mnencode(b"avocado"))
    [('bicycle', 'visible', 'robert'), ('cloud', 'unicorn', 'jet')]

    :param bytes data:
        The binary data to encode.
    :returns:
        A list of tuples of between one and three words from the wordlist.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError((
            "expected bytes or bytearray, got {cls}"
        ).format(cls=type(data).__name__))

    for block in chunk_sequence(data, 4):
        yield tuple(_block_to_words(block))


def mnformat(data, word_separator="-", group_separator="--"):
    """Encode a byte array as a sequence of grouped words, formatted as a
    single string.

    >>> mnformat(b"cucumber")
    'paris-pearl-ultra--gentle-press-total'

    :param bytes data:
        The binary data to encode.
    :param str word_separator:
        String that should be used to separate words within a group.
    :param str word_separator:
        String that should be used to separate groups of words.
    :return str:
        The data as an sequence of grouped words.
    """
    return group_separator.join(
        word_separator.join(group) for group in mnencode(data)
    )


def _words_to_block(words):
    if not isinstance(words, tuple):
        raise TypeError("expected tuple of words")

    if len(words) == 0:
        raise ValueError("no words in block")

    if len(words) > 3:
        raise ValueError("too many words in block")

    try:
        indices = list(word_to_index(word) for word in words)
    except KeyError as e:
        raise ValueError("word not recognized") from e

    # Calculate length of block.
    # Both three byte and four byte blocks map to three words but can be
    # distinguished as a different word list is used to encode the last word
    # in the three byte case.
    length = {
        1: 1,
        2: 2,
        3: 3 if indices[-1] >= 1626 else 4,
    }[len(words)]

    if length == 3:
        indices[2] -= 1626

    # Check that words in the second word list don't appear anywhere else in
    # the block.
    for index in indices:
        if index > 1626:
            raise ValueError((
                "unexpected three byte word: {word!r}"
            ).format(word=index_to_word(index)))

    num = from_base(1626, reversed(indices))

    block = bytes(reversed(to_base(256, num)))

    # Pad to correct length.
    return block.ljust(length, b'\x00')


def mndecode(data):
    """Decode an iterator of tuples of words to get a byte array

    >>> mndecode([('turtle', 'special', 'recycle'), ('ferrari', 'album')])
    b'potato'

    :param data:
        An iterator of tuples of between one and three words from the wordlist
    :return bytes:
        A :class:`bytes` object containing the decoded data
    """
    return b''.join(_words_to_block(words) for words in data)


def mnparse(string, word_separator="-", group_separator="--"):
    """Decode a mnemonicode string into a byte array.

    >>> mnparse('scoop-limit-recycle--ferrari-album')
    b'tomato'

    :param str string:
        The string containing the mnemonicode encoded data.
    :param str word_separator:
        String used to separate individual words in a group.
    :param str group_separator:
        String used to separate groups of words representing four byte blocks.
    :return bytes:
        A :class:`bytes` object containing the decoded data
    """
    if not isinstance(string, str):
        raise TypeError((
            "expected string, got {cls}"
        ).format(cls=type(string).__name__))

    # Empty string is a valid input but ``"".split(...)`` does not return an
    # empty iterator so we need to special case it.
    if len(string) == 0:
        return b''

    return mndecode(
        tuple(group.split(word_separator))
        for group in string.split(group_separator)
    )


__all__ = ['mnencode', 'mnformat', 'mndecode', 'mnparse']
