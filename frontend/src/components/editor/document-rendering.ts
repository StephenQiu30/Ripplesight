/** Keep author HTML inert and use the API's anchors, including root-file headings. */
export function documentRemark(sections: HotKeyAPI.WorkspaceSection[]) {
  return function plugin() {
    return (tree: unknown) => {
      let heading = 0;
      const walk = (value: unknown) => {
        if (!value || typeof value !== "object") return;
        const node = value as Record<string, unknown>;
        if (node.type === "html") {
          const html = String(node.value ?? "");
          node.type = "text";
          node.value = /^<!--[\s\S]*-->$/.test(html) ? "" : html;
        }
        if (node.type === "heading") {
          node.data = {
            ...(node.data as object),
            hProperties: { id: sections[heading++]?.anchor },
          };
        }
        if (Array.isArray(node.children)) node.children.forEach(walk);
      };
      walk(tree);
    };
  };
}
