import { Card, CardContent } from "@/components/ui/card";
import type { ReactNode } from "react";

interface Props {
  icon: string;
  title: string;
  body: string;
  actions?: ReactNode;
}

export function EmptyState({ icon, title, body, actions }: Props) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center">
        <div aria-hidden="true" className="text-4xl">{icon}</div>
        <div className="space-y-1">
          <div className="font-mono text-sm font-semibold uppercase tracking-wider text-foreground">
            {title}
          </div>
          <p className="max-w-md text-sm text-muted-foreground">{body}</p>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </CardContent>
    </Card>
  );
}
