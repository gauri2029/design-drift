/** Pull the file key and node id out of a Figma link.
 *
 * Asking a designer for a "file key" and a "node id" asks them to read a URL
 * and retype two substrings of it. Both are already in the link Figma hands
 * you from "Copy link to selection", so take the link.
 *
 * Returns null rather than guessing: a file link with no frame selected
 * genuinely does not say which node to compare, and inventing one surfaces
 * later as a confusing 404 from the Figma API.
 */
export function parseFigmaUrl(input: string): { fileKey: string; nodeId: string } | null {
  let url: URL
  try {
    url = new URL(input.trim())
  } catch {
    return null
  }

  if (!/(^|\.)figma\.com$/.test(url.hostname)) return null

  // /design/KEY/Name is current; /file/ and /proto/ are older forms, and
  // links of that age are still pasted around.
  const path = url.pathname.match(/^\/(?:design|file|proto)\/([A-Za-z0-9]+)/)
  if (!path) return null

  const node = url.searchParams.get('node-id')
  if (!node) return null

  // Node ids are hyphenated in URLs and colon-separated in the API, and
  // older links percent-encode the colon directly.
  const nodeId = decodeURIComponent(node).replace(/-/g, ':')
  if (!/^\d+:\d+$/.test(nodeId)) return null

  return { fileKey: path[1], nodeId }
}
