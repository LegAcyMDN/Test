export function validateEnv(requiredKeys = []) {
  const missing = requiredKeys.filter(k => !process.env[k]);
  if (missing.length) {
    const list = missing.map(k => `- ${k}`).join('\n');
    throw new Error(
      `Variables d'environnement manquantes:\n${list}\n` +
      `Crée un fichier .env (copie .env.example) et remplis ces valeurs.`
    );
  }
}
