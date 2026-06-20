export type MessageSegmentType = 'text' | 'latex_inline' | 'latex_block' | 'cite' | 'kg_cite'

export interface MessageSegment {
  type: MessageSegmentType
  content: string
}

function canMerge(left: MessageSegment | undefined, right: MessageSegment) {
  return Boolean(left) && left?.type === 'text' && right.type === 'text'
}

export function mergeAdjacentTextSegments<T extends MessageSegment>(segments: T[]): T[] {
  return segments.reduce<T[]>((merged, segment) => {
    const previous = merged[merged.length - 1]
    if (canMerge(previous, segment)) {
      merged[merged.length - 1] = {
        ...previous,
        content: `${previous.content}${segment.content}`,
      } as T
      return merged
    }

    merged.push(segment)
    return merged
  }, [])
}

export function appendMergedSegments<T extends MessageSegment>(existing: T[], incoming: T[]): T[] {
  if (!incoming.length) return existing
  return mergeAdjacentTextSegments([...existing, ...incoming])
}
