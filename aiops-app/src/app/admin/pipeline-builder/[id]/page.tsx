"use client";

import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

const BuilderLayout = dynamic(() => import("@/components/pipeline-builder/BuilderLayout"), {
  ssr: false,
});

export default function EditPipelinePage() {
  const params = useParams();
  const idStr = Array.isArray(params.id) ? params.id[0] : params.id;
  const id = idStr ? Number(idStr) : undefined;
  if (!id || Number.isNaN(id)) {
    return <div style={{ padding: 40, textAlign: "center", color: "#cf1322" }}>無效的 pipeline id</div>;
  }
  return <BuilderLayout mode="edit" pipelineId={id} />;
}
