export function decodeDocumentPath(segments: string[]) {
  return segments
    .map((segment) => {
      const decoded = decodeURIComponent(segment);
      if (
        !decoded ||
        decoded.includes("/") ||
        decoded.includes("\\") ||
        decoded.startsWith(".")
      )
        throw new Error("invalid_document_path");
      return decoded;
    })
    .join("/");
}
