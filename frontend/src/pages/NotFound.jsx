import { Link } from "react-router";
import { Compass } from "lucide-react";
import { GlassCard } from "../components/ui/GlassCard";
import { EmptyState } from "../components/ui/EmptyState";
import { Button } from "../components/ui/Button";

export default function NotFound() {
  return (
    <GlassCard>
      <EmptyState icon={Compass} title="This page does not exist"
        text="The link may be old, or the page was moved. Use Ctrl + K to jump to any page or national code."
        action={<Link to="/"><Button variant="glass">Back to the dashboard</Button></Link>} />
    </GlassCard>
  );
}
