export function nodeBaseLabel(node) {
  if (!node) return ''
  return `${node.code || ''} ${node.name || ''}`.trim()
}

export function nodeLevelLabel(node) {
  if (!node) return ''
  return `${node.level}级 ${nodeBaseLabel(node)}`
}

export function buildHierarchyTree(list = [], options = {}) {
  const {
    disabled,
    extra,
  } = options
  const byId = new Map()
  for (const item of list) {
    byId.set(item.id, {
      ...item,
      ...(extra ? extra(item) : {}),
      children: [],
      orphaned: false,
    })
  }

  const roots = []
  for (const node of byId.values()) {
    if (node.parent_id && byId.has(node.parent_id)) {
      byId.get(node.parent_id).children.push(node)
    } else {
      if (node.parent_id) node.orphaned = true
      roots.push(node)
    }
  }

  const sortNodes = (items, ancestors = []) => {
    items.sort((a, b) => {
      const sortA = Number(a.sort_order ?? 0)
      const sortB = Number(b.sort_order ?? 0)
      return sortA - sortB || Number(a.id ?? 0) - Number(b.id ?? 0)
    })
    for (const node of items) {
      const path = [...ancestors, node]
      node.path = path
      node.pathLabel = path.map(nodeBaseLabel).filter(Boolean).join(' / ')
      node.displayLabel = nodeLevelLabel(node)
      node.disabled = disabled ? Boolean(disabled(node)) : false
      sortNodes(node.children, path)
    }
  }

  sortNodes(roots)
  return roots
}

export function flattenTree(tree = []) {
  const rows = []
  const visit = (nodes) => {
    for (const node of nodes) {
      rows.push(node)
      if (node.children?.length) visit(node.children)
    }
  }
  visit(tree)
  return rows
}

export function findNodeById(tree = [], id) {
  if (id == null) return null
  for (const node of flattenTree(tree)) {
    if (node.id === id) return node
  }
  return null
}

export const treeSelectProps = {
  label: 'pathLabel',
  children: 'children',
  disabled: 'disabled',
}
