/**
 * Decoder for the `#suumoviz-obf/1` files written by the Python package
 * (src/suumoviz/codec.py). Light obfuscation, not encryption: every line after the
 * header is base64 of the original line XOR-ed with KEY (restarting at each line).
 */

export const MAGIC = '#suumoviz-obf/1'

// sha256("suumoviz/obf/1"): the same bytes as codec.KEY in Python
const KEY = Uint8Array.from(
  '63bc3e0e7deebf9dd10486861648bc76c358fc9f09facb0664109292fe499ace'.match(/../g)!,
  (hex) => parseInt(hex, 16),
)

function decodeLine(line: string): Uint8Array {
  const binary = atob(line)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i) ^ KEY[i % KEY.length]
  }
  return bytes
}

/** Plain text of an encoded file; throws when `text` is not in the format. */
export function decode(text: string): string {
  const lines = text.split('\n').map((line) => line.replace(/\r$/, ''))
  if (lines[0] !== MAGIC) throw new Error('数据文件格式不正确')
  const utf8 = new TextDecoder('utf-8', { fatal: true })
  // "\n" never occurs inside a multi-byte UTF-8 sequence, so lines decode on their own
  return lines
    .slice(1)
    .map((line) => utf8.decode(decodeLine(line)))
    .join('\n')
}
