#!/usr/bin/env node
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const SCRIPT_DIR = path.resolve(__dirname, '..', 'scripts');
const PYTHON_SCRIPT = path.join(SCRIPT_DIR, 'weread.py');

// 检查 Python 是否可用
function checkPython() {
  return new Promise((resolve, reject) => {
    const proc = spawn('python3', ['--version']);
    proc.on('close', (code) => {
      if (code === 0) resolve('python3');
      else {
        // 尝试 python
        const proc2 = spawn('python', ['--version']);
        proc2.on('close', (code2) => {
          if (code2 === 0) resolve('python');
          else reject(new Error('Python 3 is required. Please install Python 3.'));
        });
      }
    });
  });
}

async function main() {
  // 检查 WEREAD_API_KEY
  if (!process.env.WEREAD_API_KEY) {
    console.error('错误: WEREAD_API_KEY 未设置，请 export WEREAD_API_KEY=wrk-xxxxxxxx');
    process.exit(1);
  }

  // 检查脚本是否存在
  if (!fs.existsSync(PYTHON_SCRIPT)) {
    console.error(`错误: 找不到脚本 ${PYTHON_SCRIPT}`);
    process.exit(1);
  }

  try {
    const pythonCmd = await checkPython();

    // 传递所有参数给 Python 脚本
    const args = [PYTHON_SCRIPT, ...process.argv.slice(2)];
    const proc = spawn(pythonCmd, args, {
      stdio: 'inherit',
      env: process.env
    });

    proc.on('close', (code) => {
      process.exit(code || 0);
    });

    proc.on('error', (err) => {
      console.error('执行错误:', err.message);
      process.exit(1);
    });
  } catch (err) {
    console.error(err.message);
    process.exit(1);
  }
}

main();
