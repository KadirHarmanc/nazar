import * as vscode from 'vscode';
import { execFile } from 'child_process';
import * as path from 'path';

interface NazarResult {
    name: string;
    type: string;
    subtype: string;
    passed: boolean;
    detail: string;
    priority: string;
    confidence: number;
    confidence_label: string;
    how_to_fix?: {
        sorun: string;
        cozum: string;
        quick_fix: string;
    };
    guide?: {
        title: string;
        risk: string;
        what: string;
        why: string;
        steps: string[];
        before: string;
        after: string;
    };
}

export class NazarDiagnostics {
    private diagnosticCollection: vscode.DiagnosticCollection;
    private pythonPath: string;
    private projectGrade: string = '';

    constructor(private context: vscode.ExtensionContext) {
        this.diagnosticCollection = vscode.languages.createDiagnosticCollection('nazar');
        this.pythonPath = vscode.workspace.getConfiguration('nazar').get<string>('pythonPath', 'python3');
        context.subscriptions.push(this.diagnosticCollection);
    }

    async scanFile(uri: vscode.Uri): Promise<void> {
        const enabled = vscode.workspace.getConfiguration('nazar').get<boolean>('enabled', true);
        if (!enabled) return;

        const workspaceFolder = vscode.workspace.getWorkspaceFolder(uri);
        if (!workspaceFolder) return;

        const projectPath = workspaceFolder.uri.fsPath;
        const filePath = uri.fsPath;

        try {
            const results = await this.runNazar(projectPath);
            this.updateDiagnostics(uri, filePath, results);
        } catch {
            // Nazar calistirilamazsa sessizce devam et
        }
    }

    async scanProject(uri: vscode.Uri): Promise<void> {
        const projectPath = uri.fsPath;
        try {
            const results = await this.runNazar(projectPath);

            // Tum dosyalar icin diagnostics guncelle
            const fileResults = new Map<string, NazarResult[]>();
            for (const r of results) {
                const detail = r.detail || '';
                const fileMatch = detail.match(/(\S+\.\w+):(\d+)/);
                if (fileMatch) {
                    const file = fileMatch[1];
                    if (!fileResults.has(file)) {
                        fileResults.set(file, []);
                    }
                    fileResults.get(file)!.push(r);
                }
            }

            for (const [file, fileRs] of fileResults) {
                const fullPath = path.join(projectPath, file);
                const fileUri = vscode.Uri.file(fullPath);
                this.updateDiagnosticsForResults(fileUri, fileRs);
            }

            // Ozet goster
            const passed = results.filter(r => r.passed).length;
            const total = results.length;
            const rate = total > 0 ? Math.round((passed / total) * 100) : 0;
            this.projectGrade = rate >= 90 ? 'A+' : rate >= 80 ? 'A' : rate >= 70 ? 'B' : rate >= 50 ? 'C' : 'D';

            vscode.window.showInformationMessage(
                `Nazar: ${this.projectGrade} (${rate}%) - ${passed}/${total} gecti`
            );
        } catch (err) {
            vscode.window.showErrorMessage(`Nazar hatasi: ${err}`);
        }
    }

    showGuide(subtype: string): void {
        const panel = vscode.window.createWebviewPanel(
            'nazarGuide',
            `Nazar: ${subtype} Rehberi`,
            vscode.ViewColumn.Beside,
            {}
        );
        // Guide icerigini Python'dan al
        const projectPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '.';
        const script = `
import json
from nazar.guides.registry import GuideRegistry
guide = GuideRegistry.get('${subtype}')
print(json.dumps(guide or {}))
`;
        execFile(this.pythonPath, ['-c', script], { cwd: projectPath }, (err, stdout) => {
            if (err || !stdout.trim()) {
                panel.webview.html = `<h2>${subtype}</h2><p>Rehber bulunamadi.</p>`;
                return;
            }
            try {
                const guide = JSON.parse(stdout.trim());
                panel.webview.html = this.renderGuideHTML(guide);
            } catch {
                panel.webview.html = `<h2>${subtype}</h2><p>Parse hatasi.</p>`;
            }
        });
    }

    dispose(): void {
        this.diagnosticCollection.dispose();
    }

    private runNazar(projectPath: string): Promise<NazarResult[]> {
        return new Promise((resolve, reject) => {
            const script = `
import json
from nazar.scanner.project_scanner import ProjectScanner
from nazar.planner.test_planner import TestPlanner
from nazar.runners.orchestrator import TestOrchestrator
scanner = ProjectScanner('.')
scan_result = scanner.scan()
planner = TestPlanner(scan_result)
test_plan = planner.create_plan()
plan_dict = test_plan.to_dict()
orch = TestOrchestrator('.', plan_dict)
results = orch.run_all()
print(json.dumps(results))
`;
            execFile(this.pythonPath, ['-c', script], {
                cwd: projectPath,
                maxBuffer: 10 * 1024 * 1024,
                timeout: 60000,
            }, (err, stdout, stderr) => {
                if (err) {
                    reject(new Error(stderr || err.message));
                    return;
                }
                try {
                    const results: NazarResult[] = JSON.parse(stdout.trim());
                    resolve(results);
                } catch {
                    reject(new Error('Nazar ciktisi parse edilemedi'));
                }
            });
        });
    }

    private updateDiagnostics(uri: vscode.Uri, filePath: string, results: NazarResult[]): void {
        const relPath = vscode.workspace.asRelativePath(filePath);
        const fileResults = results.filter(r => {
            if (r.passed) return false;
            const detail = r.detail || '';
            return detail.includes(relPath) || detail.includes(path.basename(filePath));
        });
        this.updateDiagnosticsForResults(uri, fileResults);
    }

    private updateDiagnosticsForResults(uri: vscode.Uri, results: NazarResult[]): void {
        const severityFilter = vscode.workspace.getConfiguration('nazar').get<string>('severityFilter', 'warning');
        const severityOrder: Record<string, number> = { info: 0, warning: 1, medium: 1, high: 2, critical: 3 };
        const minSeverity = severityOrder[severityFilter] ?? 1;

        const diagnostics: vscode.Diagnostic[] = [];

        for (const r of results) {
            if (r.passed) continue;
            const resultSeverity = severityOrder[r.priority] ?? 1;
            if (resultSeverity < minSeverity) continue;

            // Satir numarasini detail'den cikart
            const detail = r.detail || '';
            const lineMatch = detail.match(/:(\d+)/);
            const line = lineMatch ? parseInt(lineMatch[1]) - 1 : 0;

            const range = new vscode.Range(
                new vscode.Position(Math.max(0, line), 0),
                new vscode.Position(Math.max(0, line), 200)
            );

            const severity = r.priority === 'critical' || r.priority === 'high'
                ? vscode.DiagnosticSeverity.Error
                : r.priority === 'medium'
                    ? vscode.DiagnosticSeverity.Warning
                    : vscode.DiagnosticSeverity.Information;

            const message = `[Nazar] ${r.name}: ${detail}`;
            const diagnostic = new vscode.Diagnostic(range, message, severity);
            diagnostic.source = 'nazar';
            diagnostic.code = r.subtype;

            // How to fix varsa
            if (r.how_to_fix) {
                diagnostic.message += `\nCozum: ${r.how_to_fix.cozum}`;
            }

            diagnostics.push(diagnostic);
        }

        this.diagnosticCollection.set(uri, diagnostics);
    }

    private renderGuideHTML(guide: Record<string, unknown>): string {
        const title = guide.title as string || 'Rehber';
        const risk = guide.risk as string || '';
        const what = guide.what as string || '';
        const why = guide.why as string || '';
        const steps = (guide.steps as string[]) || [];
        const before = guide.before as string || '';
        const after = guide.after as string || '';
        const warning = guide.warning as string || '';

        return `<!DOCTYPE html>
<html>
<head>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px; line-height: 1.6; }
h2 { color: #e74c3c; border-bottom: 2px solid #e74c3c; padding-bottom: 8px; }
.risk { background: #fef3cd; padding: 12px; border-radius: 6px; margin: 12px 0; }
.steps { background: #d4edda; padding: 12px; border-radius: 6px; }
.steps ol { margin: 8px 0; padding-left: 20px; }
.code { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-family: monospace; white-space: pre-wrap; margin: 8px 0; }
.before { border-left: 4px solid #e74c3c; }
.after { border-left: 4px solid #27ae60; }
.warning { background: #f8d7da; padding: 12px; border-radius: 6px; margin: 12px 0; }
</style>
</head>
<body>
<h2>${title}</h2>
<div class="risk"><strong>Risk:</strong> ${risk}</div>
<p><strong>Ne:</strong> ${what}</p>
<p><strong>Neden:</strong> ${why}</p>
<div class="steps">
<strong>Nasil Duzeltilir:</strong>
<ol>${steps.map(s => `<li>${s}</li>`).join('')}</ol>
</div>
<p><strong>Once:</strong></p>
<div class="code before">${before}</div>
<p><strong>Sonra:</strong></p>
<div class="code after">${after}</div>
${warning ? `<div class="warning"><strong>Uyari:</strong> ${warning}</div>` : ''}
</body>
</html>`;
    }
}
