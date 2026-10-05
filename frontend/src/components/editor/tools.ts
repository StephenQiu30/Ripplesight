import type { EditorConfig, ToolConstructable } from "@editorjs/editorjs";

/** These packages touch the DOM on import, so keep every runtime import lazy. */
export async function loadEditor() {
  const [core, header, list, quote, code, table, delimiter, inlineCode, image] =
    await Promise.all([
      import("@editorjs/editorjs"),
      import("@editorjs/header"),
      import("@editorjs/list"),
      import("@editorjs/quote"),
      import("@editorjs/code"),
      import("@editorjs/table"),
      import("@editorjs/delimiter"),
      import("@editorjs/inline-code"),
      import("@editorjs/simple-image"),
    ]);
  // Official tools publish differing constructor types; the runtime follows Editor.js's Tool API.
  const tool = (value: unknown) => value as ToolConstructable;
  const tools: EditorConfig["tools"] = {
    header: {
      class: tool(header.default),
      inlineToolbar: true,
      config: { levels: [1, 2, 3, 4, 5, 6], defaultLevel: 2 },
    },
    list: { class: tool(list.default), inlineToolbar: true },
    quote: { class: tool(quote.default), inlineToolbar: true },
    code: tool(code.default),
    table: { class: tool(table.default), inlineToolbar: true },
    delimiter: tool(delimiter.default),
    inlineCode: tool(inlineCode.default),
    image: tool(image.default),
  };
  return { EditorJS: core.default, tools };
}

export const editorI18n: EditorConfig["i18n"] = {
  messages: {
    ui: {
      blockTunes: {
        toggler: {
          "Click to tune": "块设置",
          "or drag to move": "拖动调整顺序",
        },
      },
      inlineToolbar: { converter: { "Convert to": "转换为" } },
      toolbar: { toolbox: { Add: "添加块", Search: "搜索" } },
      popover: {
        Filter: "搜索",
        "Nothing found": "没有匹配的工具",
        "Convert to": "转换为",
      },
    },
    toolNames: {
      Text: "段落",
      Heading: "标题",
      List: "列表",
      "Unordered List": "无序列表",
      "Ordered List": "有序列表",
      Checklist: "任务列表",
      Quote: "引用",
      Code: "代码块",
      Table: "表格",
      Delimiter: "分隔线",
      Image: "图片",
      Bold: "加粗",
      Italic: "斜体",
      Link: "链接",
      "Inline Code": "行内代码",
    },
    tools: {
      link: { "Add a link": "输入链接" },
      header: {
        "Heading 1": "一级标题",
        "Heading 2": "二级标题",
        "Heading 3": "三级标题",
        "Heading 4": "四级标题",
        "Heading 5": "五级标题",
        "Heading 6": "六级标题",
      },
      list: {
        Unordered: "无序列表",
        Ordered: "有序列表",
        Checklist: "任务列表",
        "Start with": "起始编号",
        Counter: "编号格式",
      },
      quote: {
        "Enter a quote": "输入引用",
        "Enter a caption": "引用来源",
        "Align Left": "左对齐",
        "Align Center": "居中",
      },
      code: { "Enter a code": "输入代码" },
      table: {
        "Add row above": "上方插入行",
        "Add row below": "下方插入行",
        "Delete row": "删除行",
        "Add column to left": "左侧插入列",
        "Add column to right": "右侧插入列",
        "Delete column": "删除列",
        "With headings": "包含表头",
        "Without headings": "无表头",
      },
    },
    blockTunes: {
      delete: { Delete: "删除", "Click to delete": "确认删除" },
      moveUp: { "Move up": "上移" },
      moveDown: { "Move down": "下移" },
    },
  },
};
