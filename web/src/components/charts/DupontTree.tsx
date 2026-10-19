interface TreeNode {
  name: string;
  value?: string;
  children?: TreeNode[];
}

interface Props {
  root: TreeNode;
}

/** 杜邦拆解树：用缩进层级呈现数学关系，避免为树形图引入额外图表库。 */
export function DupontTree({ root }: Props) {
  return (
    <div className="font-mono text-xs leading-relaxed">
      <TreeRow node={root} depth={0} />
    </div>
  );
}

function TreeRow({ node, depth }: { node: TreeNode; depth: number }) {
  const hasChildren = Boolean(node.children?.length);
  return (
    <div>
      <div
        className="flex items-center gap-2 rounded px-1 py-0.5 hover:bg-ink-50"
        style={{ paddingLeft: depth * 16 }}
      >
        <span className="text-ink-300">{hasChildren ? "▾" : "·"}</span>
        <span className={hasChildren ? "font-semibold text-ink-900" : "text-ink-700"}>
          {node.name}
        </span>
        {node.value && <span className="ml-auto text-ink-500">{node.value}</span>}
      </div>
      {node.children?.map((child) => (
        <TreeRow key={`${depth}-${child.name}`} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}
