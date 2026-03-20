"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.NazarDiagnostics = void 0;
const vscode = __importStar(require("vscode"));
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
/** Severity siralamasi: nazar priority -> VS Code DiagnosticSeverity */
const SEVERITY_MAP = {
    critical: vscode.DiagnosticSeverity.Error,
    high: vscode.DiagnosticSeverity.Warning,
    medium: vscode.DiagnosticSeverity.Information,
    low: vscode.DiagnosticSeverity.Hint,
};
const SEVERITY_ORDER = {
    low: 0,
    medium: 1,
    high: 2,
    critical: 3,
};
class NazarDiagnostics {
    context;
    outputChannel;
    diagnosticCollection;
    pythonPath;
    lastReport = null;
    /** subtype -> NazarResult eslesmesi (code action icin) */
    resultsByUri = new Map();
    constructor(context, outputChannel) {
        this.context = context;
        this.outputChannel = outputChannel;
        this.diagnosticCollection = vscode.languages.createDiagnosticCollection('nazar');
        this.pythonPath = vscode.workspace.getConfiguration('nazar').get('pythonPath', 'python3');
        context.subscriptions.push(this.diagnosticCollection);
    }
    // --- Genel erisim ---
    getLastReport() {
        return this.lastReport;
    }
    getResultsForUri(uri) {
        return this.resultsByUri.get(uri.toString()) || [];
    }
    // --- Dosya tarama ---
    async scanFile(uri) {
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(uri);
        if (!workspaceFolder) {
            return null;
        }
        const projectPath = workspaceFolder.uri.fsPath;
        try {
            const results = await this.runNazar(projectPath);
            const relPath = vscode.workspace.asRelativePath(uri.fsPath);
            const fileResults = results.filter(r => {
                if (r.passed) {
                    return false;
                }
                const detail = r.detail || '';
                return detail.includes(relPath) || detail.includes(path.basename(uri.fsPath));
            });
            this.resultsByUri.set(uri.toString(), fileResults);
            this.updateDiagnosticsForResults(uri, fileResults);
            const grade = this.buildReport(results);
            return grade;
        }
        catch (err) {
            this.outputChannel.appendLine(`[Nazar] Tarama hatasi: ${err}`);
            return null;
        }
    }
    // --- Proje tarama ---
    async scanProject(uri) {
        const projectPath = uri.fsPath;
        try {
            const results = await this.runNazar(projectPath);
            // Dosya bazli gruplama
            const fileGroups = new Map();
            for (const r of results) {
                if (r.passed) {
                    continue;
                }
                const detail = r.detail || '';
                const fileMatch = detail.match(/(\S+\.\w+):(\d+)/);
                if (fileMatch) {
                    const file = fileMatch[1];
                    if (!fileGroups.has(file)) {
                        fileGroups.set(file, []);
                    }
                    fileGroups.get(file).push(r);
                }
            }
            for (const [file, fileResults] of fileGroups) {
                const fullPath = path.join(projectPath, file);
                const fileUri = vscode.Uri.file(fullPath);
                this.resultsByUri.set(fileUri.toString(), fileResults);
                this.updateDiagnosticsForResults(fileUri, fileResults);
            }
            const grade = this.buildReport(results);
            const passed = results.filter(r => r.passed).length;
            const total = results.length;
            const rate = total > 0 ? Math.round((passed / total) * 100) : 0;
            vscode.window.showInformationMessage(`Nazar: ${grade} (${rate}%) - ${passed}/${total} gecti`);
            return grade;
        }
        catch (err) {
            this.outputChannel.appendLine(`[Nazar] Proje tarama hatasi: ${err}`);
            vscode.window.showErrorMessage(`Nazar hatasi: ${err}`);
            return null;
        }
    }
    // --- Rehber goster ---
    showGuide(subtype) {
        const panel = vscode.window.createWebviewPanel('nazarGuide', `Nazar: ${subtype} Rehberi`, vscode.ViewColumn.Beside, {});
        const projectPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '.';
        const script = `
import json
from nazar.guides.registry import GuideRegistry
guide = GuideRegistry.get('${subtype}')
print(json.dumps(guide or {}))
`;
        (0, child_process_1.execFile)(this.pythonPath, ['-c', script], { cwd: projectPath }, (err, stdout) => {
            if (err || !stdout.trim()) {
                panel.webview.html = `<h2>${subtype}</h2><p>Rehber bulunamadi.</p>`;
                return;
            }
            try {
                const guide = JSON.parse(stdout.trim());
                panel.webview.html = this.renderGuideHTML(guide);
            }
            catch {
                panel.webview.html = `<h2>${subtype}</h2><p>Parse hatasi.</p>`;
            }
        });
    }
    dispose() {
        this.diagnosticCollection.dispose();
    }
    // --- Nazar CLI calistir ---
    runNazar(projectPath) {
        return new Promise((resolve, reject) => {
            const profile = vscode.workspace.getConfiguration('nazar').get('profile', 'default');
            const script = `
import json, sys
from nazar.scanner.project_scanner import ProjectScanner
from nazar.planner.test_planner import TestPlanner
from nazar.runners.orchestrator import TestOrchestrator
scanner = ProjectScanner('.')
scan_result = scanner.scan()
planner = TestPlanner(scan_result)
test_plan = planner.create_plan(profile='${profile}')
plan_dict = test_plan.to_dict()
orch = TestOrchestrator('.', plan_dict)
results = orch.run_all()
print(json.dumps(results))
`;
            this.outputChannel.appendLine(`[Nazar] Python calistiriliyor: ${this.pythonPath}`);
            this.outputChannel.appendLine(`[Nazar] Proje yolu: ${projectPath}`);
            this.outputChannel.appendLine(`[Nazar] Profil: ${profile}`);
            (0, child_process_1.execFile)(this.pythonPath, ['-c', script], {
                cwd: projectPath,
                maxBuffer: 10 * 1024 * 1024,
                timeout: 120000,
            }, (err, stdout, stderr) => {
                if (err) {
                    this.outputChannel.appendLine(`[Nazar] HATA: ${stderr || err.message}`);
                    reject(new Error(stderr || err.message));
                    return;
                }
                if (stderr) {
                    this.outputChannel.appendLine(`[Nazar] stderr: ${stderr}`);
                }
                try {
                    const results = JSON.parse(stdout.trim());
                    this.outputChannel.appendLine(`[Nazar] ${results.length} sonuc alindi.`);
                    resolve(results);
                }
                catch {
                    this.outputChannel.appendLine(`[Nazar] JSON parse hatasi.`);
                    reject(new Error('Nazar ciktisi parse edilemedi'));
                }
            });
        });
    }
    // --- Diagnostics guncelleme ---
    updateDiagnosticsForResults(uri, results) {
        const severitySetting = vscode.workspace.getConfiguration('nazar').get('severity', 'medium');
        const minSeverity = SEVERITY_ORDER[severitySetting] ?? 1;
        const diagnostics = [];
        for (const r of results) {
            if (r.passed) {
                continue;
            }
            const resultSeverity = SEVERITY_ORDER[r.priority] ?? 1;
            if (resultSeverity < minSeverity) {
                continue;
            }
            // Satir numarasini detail'den cikart
            const detail = r.detail || '';
            const lineMatch = detail.match(/:(\d+)/);
            const line = lineMatch ? parseInt(lineMatch[1]) - 1 : 0;
            const range = new vscode.Range(new vscode.Position(Math.max(0, line), 0), new vscode.Position(Math.max(0, line), 1000));
            const severity = SEVERITY_MAP[r.priority] ?? vscode.DiagnosticSeverity.Information;
            let message = `[Nazar] ${r.name}: ${detail}`;
            if (r.how_to_fix) {
                message += `\nSorun: ${r.how_to_fix.sorun}`;
                message += `\nCozum: ${r.how_to_fix.cozum}`;
            }
            const diagnostic = new vscode.Diagnostic(range, message, severity);
            diagnostic.source = 'nazar';
            diagnostic.code = r.subtype;
            diagnostics.push(diagnostic);
        }
        this.diagnosticCollection.set(uri, diagnostics);
        this.outputChannel.appendLine(`[Nazar] ${uri.fsPath}: ${diagnostics.length} sorun bulundu.`);
    }
    // --- Rapor olustur ---
    buildReport(results) {
        const passed = results.filter(r => r.passed).length;
        const total = results.length;
        const failed = total - passed;
        const score = total > 0 ? Math.round((passed / total) * 100) : 100;
        const grade = score >= 95 ? 'A+' : score >= 85 ? 'A' : score >= 70 ? 'B' : score >= 50 ? 'C' : score >= 30 ? 'D' : 'F';
        const reportItems = results.map(r => ({
            name: r.name,
            type: r.type,
            subtype: r.subtype,
            passed: r.passed,
            detail: r.detail,
            priority: r.priority,
        }));
        this.lastReport = {
            grade,
            score,
            total,
            passed,
            failed,
            results: reportItems,
        };
        return grade;
    }
    // --- Rehber HTML ---
    renderGuideHTML(guide) {
        const title = guide.title || 'Rehber';
        const risk = guide.risk || '';
        const what = guide.what || '';
        const why = guide.why || '';
        const steps = guide.steps || [];
        const before = guide.before || '';
        const after = guide.after || '';
        const warning = guide.warning || '';
        return `<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; line-height: 1.6; }
h2 { color: #e74c3c; border-bottom: 2px solid #e74c3c; padding-bottom: 8px; }
.risk { background: #fef3cd; padding: 12px; border-radius: 6px; margin: 12px 0; color: #333; }
.steps { background: #d4edda; padding: 12px; border-radius: 6px; color: #333; }
.steps ol { margin: 8px 0; padding-left: 20px; }
.code { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-family: 'Fira Code', monospace; white-space: pre-wrap; margin: 8px 0; }
.before { border-left: 4px solid #e74c3c; }
.after { border-left: 4px solid #27ae60; }
.warning { background: #f8d7da; padding: 12px; border-radius: 6px; margin: 12px 0; color: #333; }
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
exports.NazarDiagnostics = NazarDiagnostics;
//# sourceMappingURL=diagnostics.js.map