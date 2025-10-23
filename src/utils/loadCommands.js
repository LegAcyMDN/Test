// src/utils/loadCommands.js
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { logger } from './logger.js';

/**
 * Charge toutes les commandes depuis src/commands/** en ESM (compatible Windows)
 * - Valide la présence de "data" et "execute"
 * - Log le détail par dossier
 * - Retourne { collection, jsonList, flatList }
 *
 * @param {import('discord.js').Collection} collection
 * @param {string} baseDir chemin absolu vers src/commands
 */
export async function loadCommands(collection, baseDir) {
  const grouped = {}; // dossier -> [names]
  const jsonList = [];
  const flatList = [];

  const folders = fs.readdirSync(baseDir).filter(f => fs.statSync(path.join(baseDir, f)).isDirectory());
  logger.info(`Découverte de ${folders.length} dossier(s) de commandes dans ${baseDir}`);

  for (const folder of folders) {
    const dir = path.join(baseDir, folder);
    const files = fs.readdirSync(dir).filter(f => f.endsWith('.js'));

    logger.info(`→ ${folder}: ${files.length} fichier(s) trouvé(s)`);
    grouped[folder] = [];

    for (const file of files) {
      const fileURL = pathToFileURL(path.join(dir, file)).href;
      let mod;
      try {
        mod = await import(fileURL);
      } catch (e) {
        logger.error(`   ✖ Échec import ${folder}/${file}`, e?.message || e);
        continue;
      }

      if (!mod?.data?.name || typeof mod?.execute !== 'function') {
        logger.warn(`   ! ${folder}/${file} ignoré: "data.name" ou "execute" manquant`);
        continue;
      }

      // Duplicate guard
      if (collection.has(mod.data.name)) {
        logger.warn(`   ! Commande "${mod.data.name}" déjà chargée (doublon).`);
        continue;
      }

      collection.set(mod.data.name, { data: mod.data, execute: mod.execute });
      jsonList.push(mod.data.toJSON());
      flatList.push(mod.data.name);
      grouped[folder].push(mod.data.name);

      logger.debug(`   ✓ ${folder}/${file} → /${mod.data.name}`);
    }

    if (grouped[folder].length) {
      logger.info(`   ✓ Chargées (${folder}): ${grouped[folder].map(n => `/${n}`).join(', ')}`);
    }
  }

  // Résumé final
  logger.info(`Total commandes chargées: ${flatList.length}`);
  if (flatList.length) {
    logger.info(`Liste: ${flatList.map(n => `/${n}`).join(', ')}`);
  }

  return { jsonList, flatList, grouped };
}
