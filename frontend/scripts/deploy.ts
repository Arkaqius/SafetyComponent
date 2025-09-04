import { Client as ScpClient } from 'node-scp';
import { Client as SshClient } from 'ssh2';
import * as dotenv from 'dotenv';
import { join } from 'path';
import chalk from 'chalk';
import { access, constants } from 'fs/promises';

dotenv.config();

const HA_URL = process.env.VITE_HA_URL;
const USERNAME = process.env.VITE_SSH_USERNAME;
const PASSWORD = process.env.VITE_SSH_PASSWORD;
const HOST_OR_IP_ADDRESS = process.env.VITE_SSH_HOSTNAME;
const PORT = 22;
const REMOTE_FOLDER_NAME = process.env.VITE_FOLDER_NAME;
const LOCAL_DIRECTORY = './dist';
const TEMP_REMOTE_PATH = `/tmp/${REMOTE_FOLDER_NAME}`; // Temporary upload path
const FINAL_REMOTE_PATH = `/www/${REMOTE_FOLDER_NAME}`;

async function checkDirectoryExists() {
  try {
    await access(LOCAL_DIRECTORY, constants.F_OK);
    return true;
  } catch (err) {
    return false;
  }
}

async function uploadFiles() {
  const client = await ScpClient({
    host: HOST_OR_IP_ADDRESS,
    port: PORT,
    username: USERNAME,
    password: PASSWORD,
  });

  console.info(chalk.blue('Uploading', `"${LOCAL_DIRECTORY}"`, 'to', `"${TEMP_REMOTE_PATH}"`));
  await client.uploadDir(LOCAL_DIRECTORY, TEMP_REMOTE_PATH);
  client.close();
  console.info(chalk.green('Files uploaded to temporary directory.'));
}

async function executeRemoteCommands() {
  const ssh = new SshClient();

  return new Promise<void>((resolve, reject) => {
    ssh
      .on('ready', () => {
        console.info(chalk.blue('Connected via SSH. Executing commands...'));

        ssh.exec(
          `echo '${PASSWORD}' | sudo -S mkdir -p ${FINAL_REMOTE_PATH} && sudo -S rm -rf ${FINAL_REMOTE_PATH}/* && sudo -S mv ${TEMP_REMOTE_PATH}/* ${FINAL_REMOTE_PATH}/ && sudo -S rm -rf ${TEMP_REMOTE_PATH}`,
          (err, stream) => {
            if (err) {
              reject(err);
            }
            stream
              .on('close', (code, signal) => {
                if (code === 0) {
                  console.info(chalk.green('Files moved successfully with sudo.'));
                  resolve();
                } else {
                  reject(new Error(`Command failed with code ${code}, signal ${signal}`));
                }
                ssh.end();
              })
              .on('data', data => {
                console.log('STDOUT:', data.toString());
              })
              .stderr.on('data', data => {
                console.error('STDERR:', data.toString());
              });
          }
        );
      })
      .on('error', err => {
        reject(err);
      })
      .connect({
        host: HOST_OR_IP_ADDRESS,
        port: PORT,
        username: USERNAME,
        password: PASSWORD,
      });
  });
}

async function deploy() {
  try {
    if (!HA_URL || !REMOTE_FOLDER_NAME || !USERNAME || !PASSWORD || !HOST_OR_IP_ADDRESS) {
      throw new Error('Missing required environment variables in .env file.');
    }

    const exists = await checkDirectoryExists();
    if (!exists) {
      throw new Error('Missing ./dist directory, have you run `npm run build`?');
    }

    await uploadFiles();
    await executeRemoteCommands();

    console.info(chalk.green('\nSuccessfully deployed!'));
    const url = join(HA_URL, '/local', REMOTE_FOLDER_NAME, '/index.html');
    console.info(chalk.blue(`\n\nVISIT the following URL to preview your dashboard:\n`));
    console.info(chalk.bgCyan(chalk.underline(url)));
    console.info(
      chalk.yellow(
        '\n\nAlternatively, follow the steps in the ha-component-kit repository to install the addon for Home Assistant so you can load your dashboard from the sidebar!\n\n'
      )
    );
    console.info('\n\n');
  } catch (e: unknown) {
    if (e instanceof Error) {
      console.error(chalk.red('Error:', e.message ?? 'unknown error'));
    }
  }
}

deploy();
