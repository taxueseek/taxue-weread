#!/usr/bin/env node
const { spawn } = require('child_process');

function checkPython() {
  return new Promise((resolve, reject) => {
    const proc = spawn('python3', ['--version']);
    let output = '';
    proc.stdout.on('data', (d) => output += d);
    proc.stderr.on('data', (d) => output += d);
    proc.on('close', (code) => {
      if (code === 0) {
        console.log(`✅ ${output.trim()}`);
        resolve();
      } else {
        // 尝试 python
        const proc2 = spawn('python', ['--version']);
        let output2 = '';
        proc2.stdout.on('data', (d) => output2 += d);
        proc2.stderr.on('data', (d) => output2 += d);
        proc2.on('close', (code2) => {
          if (code2 === 0) {
            console.log(`✅ ${output2.trim()}`);
            resolve();
          } else {
            console.error('❌ Python 3 is required but not found.');
            console.error('   Install Python 3: https://www.python.org/downloads/');
            reject(new Error('Python 3 not found'));
          }
        });
      }
    });
  });
}

checkPython().catch(() => process.exit(1));
