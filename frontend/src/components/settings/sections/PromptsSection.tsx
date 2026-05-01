import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingsAccordion } from "../SettingsAccordion";
import { Button } from "@/components/ui/button";
import { DirectoryPicker } from "@/components/picker/DirectoryPicker";
import {
  useProjectSettings,
  useProjectSettingsMutation,
} from "@/hooks/useProjectSettings";

interface Props {
  slug: string;
}

function toLocal(value: string | null): string {
  return value ?? "";
}

function toServer(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

export function PromptsSection({ slug }: Props) {
  const { t } = useTranslation();
  const { data } = useProjectSettings(slug);
  const mut = useProjectSettingsMutation(slug);

  const server = data?.prompts;
  const [systemPath, setSystemPath] = useState("");
  const [extractUserPath, setExtractUserPath] = useState("");
  const [pickingSystem, setPickingSystem] = useState(false);
  const [pickingExtract, setPickingExtract] = useState(false);

  useEffect(() => {
    if (server) {
      // Server-data sync into local form state — intentional initialization pattern.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSystemPath(toLocal(server.custom_system_path));
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setExtractUserPath(toLocal(server.custom_extract_user_path));
    }
  }, [server]);

  if (!data || !server) return null;

  const localSystem = toServer(systemPath);
  const localExtract = toServer(extractUserPath);

  const dirty =
    localSystem !== server.custom_system_path ||
    localExtract !== server.custom_extract_user_path;

  const onSave = () => {
    mut.mutate({
      prompts: {
        custom_system_path: localSystem,
        custom_extract_user_path: localExtract,
      },
    });
  };

  return (
    <SettingsAccordion
      title={t("settings.section.prompts.title")}
      dirty={dirty}
      saving={mut.isPending}
      onSave={onSave}
      errorMessage={mut.isError ? (mut.error as Error).message : null}
    >
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          {t("settings.section.prompts.custom_system_path")}
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={systemPath}
            onChange={(e) => setSystemPath(e.target.value)}
            className="flex-1 rounded-md border bg-background px-2 py-1 font-mono text-xs"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setPickingSystem(true)}
          >
            {t("settings.section.prompts.browse")}
          </Button>
        </div>
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">
          {t("settings.section.prompts.custom_extract_user_path")}
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={extractUserPath}
            onChange={(e) => setExtractUserPath(e.target.value)}
            className="flex-1 rounded-md border bg-background px-2 py-1 font-mono text-xs"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setPickingExtract(true)}
          >
            {t("settings.section.prompts.browse")}
          </Button>
        </div>
      </div>

      <DirectoryPicker
        open={pickingSystem}
        mode="file"
        fileExtensions={[".md", ".txt"]}
        onSelect={(path) => {
          setSystemPath(path);
          setPickingSystem(false);
        }}
        onClose={() => setPickingSystem(false)}
      />
      <DirectoryPicker
        open={pickingExtract}
        mode="file"
        fileExtensions={[".md", ".txt"]}
        onSelect={(path) => {
          setExtractUserPath(path);
          setPickingExtract(false);
        }}
        onClose={() => setPickingExtract(false)}
      />
    </SettingsAccordion>
  );
}
