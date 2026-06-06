// Minimal zip reader for the STORED (no-compression) format.
//
// The backend's /api/generate/zip endpoint encodes with ZIP_STORED on
// purpose (host-sim outputs are KB-scale C/H files that don't benefit
// from DEFLATE). This module gives us a dependency-free way to crack
// that zip in the browser when the user picks "Save to folder" via
// `window.showDirectoryPicker`. If you ever need DEFLATE here, swap to
// `DecompressionStream("deflate-raw")` — but keep the backend's
// `compress_type` test in sync, the contract is intentionally narrow.
//
// Zip layout this reader understands (per ISO/IEC 21320-1 / PKWARE
// APPNOTE.TXT §4.3.7):
//
//   loop:
//     0x04034b50  Local File Header (30 fixed bytes)
//                   name (nameLen)
//                   extra (extraLen)
//                   data (compSize)
//   then:
//     0x02014b50  Central Directory (ignored)
//     0x06054b50  End of Central Directory (ignored)

export type UnzipEntry = { path: string; content: Uint8Array };

const SIG_LFH = 0x04034b50;

/** Parse a STORED zip blob into its entries. Throws on any compressed
 *  entry — we want a loud break, not a silent partial save. */
export async function unzipStored(blob: Blob): Promise<UnzipEntry[]> {
  const buf = new Uint8Array(await blob.arrayBuffer());
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const entries: UnzipEntry[] = [];
  const dec = new TextDecoder("utf-8");
  let off = 0;

  while (off + 30 <= buf.length) {
    const sig = dv.getUint32(off, true);
    if (sig !== SIG_LFH) break; // CD / EOCD / unknown — stop iteration.
    const method = dv.getUint16(off + 8, true);
    const compSize = dv.getUint32(off + 18, true);
    const nameLen = dv.getUint16(off + 26, true);
    const extraLen = dv.getUint16(off + 28, true);
    const dataStart = off + 30 + nameLen + extraLen;
    const path = dec.decode(buf.subarray(off + 30, off + 30 + nameLen));
    if (method !== 0) {
      throw new Error(
        `zip entry "${path}" is not STORED (method=${method}); ` +
          "the backend should always emit ZIP_STORED — see /api/generate/zip.",
      );
    }
    const content = buf.slice(dataStart, dataStart + compSize);
    if (!isDirectoryEntry(path, content)) {
      entries.push({ path, content });
    }
    off = dataStart + compSize;
  }
  return entries;
}

function isDirectoryEntry(path: string, content: Uint8Array): boolean {
  // Defensive: most writers omit directory entries entirely, but the
  // zip spec allows zero-byte entries whose name ends with "/". Skip
  // those so we don't try to call createWritable() on a directory.
  return path.endsWith("/") && content.length === 0;
}
