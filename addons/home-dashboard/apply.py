"""Build the pinned household overlay in a staging directory, never in-place."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def transform(data, spec):
    if digest(data) != spec['input_sha256']:
        raise ValueError('Unexpected input build; refusing to patch')
    source = data.decode('utf-8')
    previous = 0
    chunks = []
    for edit in spec['edits']:
        start, end = edit['start'], edit['end']
        if not previous <= start <= end <= len(source):
            raise ValueError('Invalid or overlapping edit range')
        chunks.extend((source[previous:start], edit['text']))
        previous = end
    chunks.append(source[previous:])
    output = ''.join(chunks).encode('utf-8')
    if digest(output) != spec['output_sha256']:
        raise ValueError('Output checksum mismatch')
    return output


def build(stock, output, manifest):
    stock, output = stock.resolve(), output.resolve()
    if stock == output or stock == Path('/') or output == Path('/'):
        raise ValueError('Use distinct, non-root staging directories')
    pending = []
    for name, spec in manifest['files'].items():
        relative = Path('www/luci-static/resources') / name
        if Path(name).is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid manifest path')
        pending.append((relative, transform((stock / relative).read_bytes(), spec)))
    # Validate every input before creating any output.
    for relative, data in pending:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.new')
        temporary.write_bytes(data)
        temporary.replace(target)
    return len(pending)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(__file__).with_name('v1.0.19-apk.json').read_text(encoding='utf-8'))
    print('Prepared', build(args.stock, args.output, manifest), 'verified overlay files')
