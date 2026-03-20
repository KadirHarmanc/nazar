import * as vscode from 'vscode';
import { NazarDiagnostics } from './diagnostics';

let diagnostics: NazarDiagnostics;

export function activate(context: vscode.ExtensionContext) {
    diagnostics = new NazarDiagnostics(context);

    // Dosya kaydedildiginde otomatik tara
    const scanOnSave = vscode.workspace.getConfiguration('nazar').get<boolean>('scanOnSave', true);
    if (scanOnSave) {
        context.subscriptions.push(
            vscode.workspace.onDidSaveTextDocument((doc) => {
                if (isSupported(doc)) {
                    diagnostics.scanFile(doc.uri);
                }
            })
        );
    }

    // Dosya acildiginda tara
    context.subscriptions.push(
        vscode.workspace.onDidOpenTextDocument((doc) => {
            if (isSupported(doc)) {
                diagnostics.scanFile(doc.uri);
            }
        })
    );

    // Komutlar
    context.subscriptions.push(
        vscode.commands.registerCommand('nazar.scanFile', () => {
            const editor = vscode.window.activeTextEditor;
            if (editor) {
                diagnostics.scanFile(editor.document.uri);
                vscode.window.showInformationMessage('Nazar: Dosya taraniyor...');
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nazar.scanProject', () => {
            const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
            if (workspaceFolder) {
                diagnostics.scanProject(workspaceFolder.uri);
                vscode.window.showInformationMessage('Nazar: Proje taraniyor...');
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('nazar.showGuide', (subtype: string) => {
            diagnostics.showGuide(subtype);
        })
    );

    // Status bar
    const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBar.text = '$(shield) Nazar';
    statusBar.tooltip = 'Nazar - Otonom Test Araci';
    statusBar.command = 'nazar.scanFile';
    statusBar.show();
    context.subscriptions.push(statusBar);

    // Mevcut acik dosyalari tara
    vscode.window.visibleTextEditors.forEach((editor) => {
        if (isSupported(editor.document)) {
            diagnostics.scanFile(editor.document.uri);
        }
    });
}

function isSupported(doc: vscode.TextDocument): boolean {
    const supported = [
        'javascript', 'typescript', 'javascriptreact', 'typescriptreact',
        'python', 'go', 'rust', 'dart', 'swift', 'kotlin', 'java',
    ];
    return supported.includes(doc.languageId);
}

export function deactivate() {
    if (diagnostics) {
        diagnostics.dispose();
    }
}
