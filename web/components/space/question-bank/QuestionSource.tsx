"use client";

import { useTranslation } from "react-i18next";
import type { QuestionSourceMetadata } from "@/lib/notebook-api";

export default function QuestionSource({
  source,
}: {
  source?: QuestionSourceMetadata | null;
}) {
  const { t } = useTranslation();
  const fields = [
    [t("Source file"), source?.filename],
    [t("Source year"), source?.year],
    [t("PDF page (1-based)"), source?.pdf_page],
    [t("Original question number"), source?.question_number],
  ];
  return (
    <dl className="mt-3 grid gap-1 text-xs text-[var(--muted-foreground)] sm:pl-[1.625rem]">
      {fields.map(([label, value]) => (
        <div key={label} className="flex flex-wrap gap-x-2 [overflow-wrap:anywhere]">
          <dt>{label}:</dt>
          <dd>{value === undefined || value === null || value === "" ? t("Unknown") : value}</dd>
        </div>
      ))}
    </dl>
  );
}
