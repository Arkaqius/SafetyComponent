import { createHash, timingSafeEqual } from 'node:crypto';
import { access, constants, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import chalk from 'chalk';
import dotenv from 'dotenv';
import { Client as ScpClient } from 'node-scp';

dotenv.config();

const localDirectory = resolve('dist');
const remoteRoot = '/config/www';
const folderName = process.env.VITE_FOLDER_NAME?.trim() || 'SafetyHome';
const targetPath = `${remoteRoot}/${folderName}`;
const stagingPath = `${remoteRoot}/.${folderName}.staging-${Date.now()}`;
const backupPath = `${remoteRoot}/.${folderName}.previous-${Date.now()}`;

function requireValue(name) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Brak wymaganej zmiennej ${name} w pliku .env.`);
  return value;
}

function validateConfiguration() {
  if (!/^[A-Za-z0-9_-]+$/.test(folderName)) {
    throw new Error('VITE_FOLDER_NAME może zawierać wyłącznie litery, cyfry, myślnik i podkreślenie.');
  }

  const port = Number(process.env.HA_SSH_PORT || 22);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error('HA_SSH_PORT musi być poprawnym numerem portu TCP.');
  }

  return {
    haUrl: new URL(requireValue('VITE_HA_URL')),
    host: requireValue('HA_SSH_HOSTNAME'),
    port,
    username: requireValue('HA_SSH_USERNAME'),
  };
}

function normalizeHostFingerprint(value) {
  if (!value.startsWith('SHA256:')) {
    throw new Error('HA_SSH_HOST_FINGERPRINT musi mieć format OpenSSH SHA256:<base64>.');
  }
  const digest = value.slice('SHA256:'.length).replace(/=+$/, '');
  const decoded = Buffer.from(digest, 'base64');
  const canonical = decoded.toString('base64').replace(/=+$/, '');
  if (decoded.length !== 32 || canonical !== digest) {
    throw new Error('HA_SSH_HOST_FINGERPRINT nie zawiera poprawnego odcisku SHA-256.');
  }
  return decoded;
}

function verifyHostKey(hostKey, expectedFingerprint) {
  const actualFingerprint = createHash('sha256').update(hostKey).digest();
  return actualFingerprint.length === expectedFingerprint.length && timingSafeEqual(actualFingerprint, expectedFingerprint);
}

async function buildConnectionOptions(configuration) {
  const password = process.env.HA_SSH_PASSWORD;
  const privateKeyPath = process.env.HA_SSH_PRIVATE_KEY_PATH?.trim();
  if (!password && !privateKeyPath) {
    throw new Error('Ustaw HA_SSH_PASSWORD albo HA_SSH_PRIVATE_KEY_PATH.');
  }

  const options = {
    host: configuration.host,
    port: configuration.port,
    username: configuration.username,
    readyTimeout: 20_000,
  };
  const expectedFingerprint = normalizeHostFingerprint(requireValue('HA_SSH_HOST_FINGERPRINT'));

  if (privateKeyPath) {
    options.privateKey = await readFile(resolve(privateKeyPath));
    if (process.env.HA_SSH_KEY_PASSPHRASE) {
      options.passphrase = process.env.HA_SSH_KEY_PASSPHRASE;
    }
  } else {
    options.password = password;
  }

  options.hostVerifier = hostKey => verifyHostKey(hostKey, expectedFingerprint);

  return options;
}

async function pathExists(client, path) {
  return Boolean(await client.exists(path));
}

async function removeIfPresent(client, path) {
  if (await pathExists(client, path)) {
    await client.rmdir(path);
  }
}

async function removeWithWarning(client, path, description) {
  try {
    await removeIfPresent(client, path);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.warn(chalk.yellow(`${description}: ${message}`));
  }
}

async function deploy() {
  const configuration = validateConfiguration();
  await access(resolve(localDirectory, 'index.html'), constants.R_OK);

  const connectionOptions = await buildConnectionOptions(configuration);
  const client = await ScpClient(connectionOptions);
  let previousVersionMoved = false;
  let stagingPresent = false;
  let promoted = false;

  try {
    if (!(await pathExists(client, remoteRoot))) {
      throw new Error(
        `${remoteRoot} nie istnieje. Utwórz katalog www w /config i uruchom ponownie Home Assistanta przed pierwszym deployem.`
      );
    }

    await removeIfPresent(client, stagingPath);
    console.info(chalk.blue(`Wysyłanie ${localDirectory} do ${stagingPath}…`));
    stagingPresent = true;
    await client.uploadDir(localDirectory, stagingPath);

    if (!(await pathExists(client, `${stagingPath}/index.html`))) {
      throw new Error('Weryfikacja uploadu nie powiodła się: brak zdalnego index.html.');
    }

    if (await pathExists(client, targetPath)) {
      await client.rename(targetPath, backupPath);
      previousVersionMoved = true;
    }

    try {
      await client.rename(stagingPath, targetPath);
      stagingPresent = false;
      promoted = true;
      if (!(await pathExists(client, `${targetPath}/index.html`))) {
        throw new Error('Weryfikacja po podmianie nie powiodła się: brak index.html.');
      }
    } catch (error) {
      let rollbackError = null;
      try {
        if (promoted && (await pathExists(client, targetPath))) {
          await client.rmdir(targetPath);
          promoted = false;
        }
        if (previousVersionMoved && !(await pathExists(client, targetPath))) {
          await client.rename(backupPath, targetPath);
          previousVersionMoved = false;
        }
      } catch (caughtRollbackError) {
        rollbackError = caughtRollbackError;
      }
      if (rollbackError) {
        const rollbackMessage = rollbackError instanceof Error ? rollbackError.message : String(rollbackError);
        const originalMessage = error instanceof Error ? error.message : String(error);
        throw new Error(`${originalMessage} Rollback także się nie powiódł: ${rollbackMessage}`);
      }
      throw error;
    }

    if (previousVersionMoved) {
      await removeWithWarning(client, backupPath, 'Nowa wersja działa, ale nie udało się usunąć poprzedniego backupu');
      previousVersionMoved = false;
    }

    const previewUrl = new URL(`/local/${folderName}/index.html`, configuration.haUrl);
    console.info(chalk.green('Frontend został wdrożony i zweryfikowany.'));
    console.info(chalk.cyan(previewUrl.toString()));
  } catch (error) {
    if (stagingPresent) {
      await removeWithWarning(client, stagingPath, 'Nie udało się usunąć niepełnego katalogu staging');
    }
    throw error;
  } finally {
    client.close();
  }
}

deploy().catch(error => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(chalk.red(`Deploy nie powiódł się: ${message}`));
  process.exitCode = 1;
});
