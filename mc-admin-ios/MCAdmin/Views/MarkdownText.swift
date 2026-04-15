import SwiftUI

/// 解析Markdown文本并渲染，支持代码块、行内代码、粗体、斜体、列表等
struct MarkdownText: View {
    let text: String

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(parseBlocks().enumerated()), id: \.offset) { _, block in
                switch block {
                case .codeBlock(let language, let code):
                    codeBlockView(language: language, code: code)
                case .text(let content):
                    inlineMarkdownText(content)
                }
            }
        }
    }

    // MARK: - 代码块视图

    private func codeBlockView(language: String, code: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if !language.isEmpty {
                Text(language)
                    .font(.caption2)
                    .foregroundStyle(Theme.textMuted)
                    .padding(.horizontal, 8)
                    .padding(.top, 6)
            }

            Text(code)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(Theme.green)
                .padding(.horizontal, 8)
                .padding(.bottom, 8)
                .padding(.top, language.isEmpty ? 8 : 2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.4))
        .cornerRadius(8)
    }

    // MARK: - 行内Markdown渲染

    private func inlineMarkdownText(_ content: String) -> some View {
        Group {
            if let attributed = try? AttributedString(
                markdown: content,
                options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
            ) {
                Text(attributed)
                    .font(.body)
                    .foregroundStyle(Theme.textPrimary)
                    .tint(Theme.primary)
            } else {
                Text(content)
                    .font(.body)
                    .foregroundStyle(Theme.textPrimary)
            }
        }
    }

    // MARK: - 解析块级元素

    private enum Block {
        case text(String)
        case codeBlock(language: String, code: String)
    }

    private func parseBlocks() -> [Block] {
        var blocks: [Block] = []
        var currentText = ""
        let lines = text.components(separatedBy: "\n")
        var i = 0

        while i < lines.count {
            let line = lines[i]

            // 检测代码块开始 ```
            if line.trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                // 先把积累的文本保存
                if !currentText.isEmpty {
                    blocks.append(.text(currentText.trimmingCharacters(in: .newlines)))
                    currentText = ""
                }

                let lang = String(line.trimmingCharacters(in: .whitespaces).dropFirst(3))
                var codeLines: [String] = []
                i += 1

                // 找到代码块结束
                while i < lines.count {
                    if lines[i].trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                        break
                    }
                    codeLines.append(lines[i])
                    i += 1
                }

                blocks.append(.codeBlock(language: lang, code: codeLines.joined(separator: "\n")))
            } else {
                if !currentText.isEmpty {
                    currentText += "\n"
                }
                currentText += line
            }

            i += 1
        }

        // 剩余文本
        if !currentText.isEmpty {
            blocks.append(.text(currentText.trimmingCharacters(in: .newlines)))
        }

        return blocks
    }
}
