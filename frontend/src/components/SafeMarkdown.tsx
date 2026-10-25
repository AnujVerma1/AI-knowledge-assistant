import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Model output is untrusted. react-markdown builds React elements (never innerHTML), skipHtml
// drops any raw HTML the model writes, and its default URL filter blocks javascript: links.
const CITATION_LABEL = /\[(S\d+)\]/g
const CITATION_HREF = '#cite-'

export function SafeMarkdown({ text, onCitationClick }: { text: string; onCitationClick: (label: string) => void }) {
  const withCitationLinks = text.replace(CITATION_LABEL, `[$1](${CITATION_HREF}$1)`)

  return (
    <div className="markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ href, children }) =>
            href?.startsWith(CITATION_HREF) ? (
              <button
                type="button"
                onClick={() => onCitationClick(href.slice(CITATION_HREF.length))}
                className="mx-0.5 inline-flex rounded bg-indigo-50 px-1.5 align-baseline text-xs font-semibold text-indigo-700 hover:bg-indigo-100"
              >
                {children}
              </button>
            ) : (
              <a href={href} target="_blank" rel="noopener noreferrer nofollow">
                {children}
              </a>
            ),
        }}
      >
        {withCitationLinks}
      </Markdown>
    </div>
  )
}
