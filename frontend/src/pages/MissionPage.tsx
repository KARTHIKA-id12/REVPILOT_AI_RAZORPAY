import { CheckCircle2, Database, ShieldAlert, ArrowRight, BrainCircuit, Activity, LineChart } from "lucide-react";
import { Link } from "react-router-dom";

export function MissionPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-8 pb-12">
      <div>
        <h1 className="text-2xl font-semibold text-[var(--color-text-primary)]">Mission Architecture & Workflow</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">
          The autonomous AI workflow of RevPilot. From raw commerce data to validated incremental revenue.
        </p>
      </div>

      {/* Workflow Diagram */}
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8">
         <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            
            {/* Step 1 */}
            <div className="flex flex-col items-center text-center p-6 border border-[var(--color-border)] rounded-xl bg-[var(--color-bg)] shadow-sm relative">
               <div className="w-12 h-12 rounded-full bg-blue-500/10 flex items-center justify-center mb-4">
                  <Database className="text-blue-500" size={24} />
               </div>
               <h3 className="font-semibold mb-2">1. Commerce Data</h3>
               <p className="text-xs text-[var(--color-text-secondary)]">Merchant CSVs and Razorpay transactions are ingested deterministically. RFM and Affinity analytics are run securely.</p>
               <ArrowRight className="hidden md:block absolute -right-5 top-1/2 -translate-y-1/2 text-[var(--color-border)]" size={24} />
            </div>

            {/* Step 2 */}
            <div className="flex flex-col items-center text-center p-6 border border-[var(--color-border)] rounded-xl bg-[var(--color-bg)] shadow-sm relative">
               <div className="w-12 h-12 rounded-full bg-[var(--color-accent)]/10 flex items-center justify-center mb-4">
                  <BrainCircuit className="text-[var(--color-accent)]" size={24} />
               </div>
               <h3 className="font-semibold mb-2">2. Autonomous Loop</h3>
               <p className="text-xs text-[var(--color-text-secondary)]">Growth Agent accepts a Goal, fetches opportunities, simulates scenarios, and runs checkout tests using the Buyer Agent.</p>
               <ArrowRight className="hidden md:block absolute -right-5 top-1/2 -translate-y-1/2 text-[var(--color-border)]" size={24} />
            </div>

            {/* Step 3 */}
            <div className="flex flex-col items-center text-center p-6 border border-[var(--color-border)] rounded-xl bg-[var(--color-bg)] shadow-sm">
               <div className="w-12 h-12 rounded-full bg-green-500/10 flex items-center justify-center mb-4">
                  <ShieldAlert className="text-green-500" size={24} />
               </div>
               <h3 className="font-semibold mb-2">3. Vital Sign-off</h3>
               <p className="text-xs text-[var(--color-text-secondary)]">If policy checks fail, the AI self-corrects. Final campaigns are drafted and await human approval in the Approval Center.</p>
            </div>

         </div>

         <div className="mt-12 border-t border-[var(--color-border)] pt-8 grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
               <h3 className="text-lg font-semibold flex items-center gap-2 mb-4"><Activity size={20} className="text-[var(--color-accent)]" /> The Final Result</h3>
               <p className="text-sm text-[var(--color-text-secondary)] mb-4">
                 The output of this system is guaranteed incremental revenue derived from deterministic math (not LLM hallucinations). Payments are safely routed through Razorpay test integrations, and attribution is strictly tracked on the ledger.
               </p>
               <ul className="space-y-2 text-sm text-[var(--color-text-primary)]">
                  <li className="flex items-center gap-2"><CheckCircle2 size={16} className="text-green-500" /> Razorpay Test Keys Verified</li>
                  <li className="flex items-center gap-2"><CheckCircle2 size={16} className="text-green-500" /> AI Budget Constraints Enforced</li>
                  <li className="flex items-center gap-2"><CheckCircle2 size={16} className="text-green-500" /> Closed Loop Analytics Ready</li>
               </ul>
            </div>

            <div className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded-xl p-6">
               <h3 className="font-semibold flex items-center gap-2 mb-4"><LineChart size={20} className="text-[var(--color-accent)]" /> Next Actions</h3>
               <p className="text-sm text-[var(--color-text-secondary)] mb-6">
                 To see the autonomous flow in action, head over to the Agent interface and set a revenue goal.
               </p>
               <Link to="/agent" className="block text-center rounded bg-[var(--color-accent)] px-4 py-2.5 text-sm font-medium text-[#1a1200] hover:opacity-90">
                 Launch Goal Mode
               </Link>
            </div>
         </div>
      </div>
    </div>
  );
}
