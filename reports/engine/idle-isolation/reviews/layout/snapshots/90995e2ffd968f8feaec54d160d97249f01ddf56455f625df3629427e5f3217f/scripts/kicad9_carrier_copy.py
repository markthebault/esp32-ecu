"""Adapt a new copy of the archived KiCad10 carrier for the Linux KiCad9 loader.

This preserves named electrical objects. It does not qualify geometry, copper,
mask processing, module fit or manufacturing. Never apply it to an archive.
"""
import hashlib
import json
import re


def chunks(text, kind):
    """Yield balanced named expressions without interpreting quoted atoms."""
    for match in re.finditer(r'\(' + re.escape(kind) + r'(?=\s|\))', text):
        depth = 0
        quoted = escape = False
        for index in range(match.start(), len(text)):
            char = text[index]
            if quoted:
                if escape:
                    escape = False
                elif char == '\\':
                    escape = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if not depth:
                    yield match.start(), index + 1, text[match.start():index + 1]
                    break
        else:
            raise ValueError('Unbalanced KiCad expression: ' + kind)


def footprint_copy(data):
    text = data.decode()
    text = text.replace('(version 20260206)', '(version 20241229)')
    removed = {}
    for kind in ('duplicate_pad_numbers_are_jumpers', 'point'):
        entries = list(chunks(text, kind))
        if kind == 'duplicate_pad_numbers_are_jumpers':
            assert all(block.strip() == '(duplicate_pad_numbers_are_jumpers no)'
                       for _, _, block in entries)
        for start, end, _ in reversed(entries):
            text = text[:start] + text[end:]
        removed[kind] = len(entries)
    return text.encode(), removed


def board_copy(data):
    assert b'(version 20260206)' in data
    text, removed = footprint_copy(data)
    text = text.decode().replace('(generator_version "10.0")', '(generator_version "9.0")')
    text, tenting = re.subn(r'\(tenting\s*\(front yes\)\s*\(back yes\)\s*\)',
                           '(tenting front back)', text)
    assert tenting == 1
    for kind in ('covering', 'plugging', 'capping', 'filling'):
        entries = list(chunks(text, kind))
        assert all('yes' not in block for _, _, block in entries)
        for start, end, _ in reversed(entries):
            text = text[:start] + text[end:]
        removed[kind] = len(entries)
    # KiCad10 uses names at every reference, rather than a global integer table.
    pattern = r'\(net ("(?:\\.|[^"\\])*")\)'
    names = sorted(set(re.findall(pattern, text)))
    codes = {name: index + 1 for index, name in enumerate(names)}
    text = re.sub(pattern, lambda m: f'(net {codes[m[1]]} {m[1]})', text)
    for kind in ('segment', 'arc', 'via', 'zone'):
        for start, end, block in reversed(list(chunks(text, kind))):
            if kind == 'zone':
                block = re.sub(r'\(net (\d+) ("(?:\\.|[^"\\])*")\)',
                               r'(net \1)\n\t\t(net_name \2)', block)
                # KiCad9 requires the explicit enabled fill atom.
                block = re.sub(r'\(fill(?=\s*\()', '(fill yes', block)
            else:
                block = re.sub(r'\(net (\d+) "(?:\\.|[^"\\])*"\)', r'(net \1)', block)
            text = text[:start] + block + text[end:]
    at = text.index('\n\t(footprint ')
    declarations = '\n\t(net 0 "")' + ''.join(f'\n\t(net {code} {name})'
                                             for name, code in codes.items())
    text = text[:at] + declarations + text[at:]
    result = text.encode()
    return result, dict(source_sha256=hashlib.sha256(data).hexdigest(),
                       adapted_sha256=hashlib.sha256(result).hexdigest(),
                       removed_metadata=removed, named_net_count=len(codes),
                       adaptations=['Format declaration and generator version',
                                    'Tenting syntax, disabled fabrication flags and construction points',
                                    'Explicit integer net table with names retained',
                                    'Explicit enabled zone-fill atom'],
                       scope='New copy only; native loader/DRC/parity and independent geometry audit required')
