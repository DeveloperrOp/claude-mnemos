import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

export default function App() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Button>{t("common.open")}</Button>
    </div>
  );
}
