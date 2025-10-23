// src/commands/admin/shards.js
import {
  SlashCommandBuilder, EmbedBuilder,
  ActionRowBuilder, ButtonBuilder, ButtonStyle
} from 'discord.js';

const PAGE_SIZE = 10;
const COL_WIDTHS = { id: 3, ping: 4, guilds: 6, users: 7, mem: 5, up: 6 };

const pad = (v, w) => `${String(v)}`.padStart(w, ' ');
const fmtMb = m => Math.round(m).toString();
const fmtUptime = ms => {
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d${h}h`;
  if (h) return `${h}h${m}m`;
  return `${m}m`;
};
const sum = (arr, key) => arr.reduce((a, x) => a + (x[key] ?? 0), 0);
const avg = (arr, key) => Math.round(arr.reduce((a, x) => a + (x[key] ?? 0), 0) / Math.max(arr.length, 1));

async function fetchShardSnapshot(client) {
  // broadcastEval est appelé une seule fois, chaque shard calcule localement ses métriques
  const results = await client.shard.broadcastEval(c => ({
    id: c.shard.ids[0],
    ping: Math.max(-1, Math.round(c.ws.ping)),
    guilds: c.guilds.cache.size,
    users: c.guilds.cache.reduce((acc, g) => acc + (g.memberCount || 0), 0),
    uptime: c.uptime,
    memoryMB: Math.round(process.memoryUsage().rss / 1024 / 1024)
  }));
  // tri par id pour un rendu stable
  return results.sort((a, b) => a.id - b.id);
}

function renderTablePage(rows, page, pageSize) {
  const start = page * pageSize;
  const slice = rows.slice(start, start + pageSize);
  const header =
    `#  ${pad('PING', COL_WIDTHS.ping)} ${pad('GUILDS', COL_WIDTHS.guilds)} ${pad('USERS', COL_WIDTHS.users)} ${pad('MEM', COL_WIDTHS.mem)} ${pad('UP', COL_WIDTHS.up)}\n` +
    `—`.repeat(4 + 1 + COL_WIDTHS.ping + 1 + COL_WIDTHS.guilds + 1 + COL_WIDTHS.users + 1 + COL_WIDTHS.mem + 1 + COL_WIDTHS.up);

  const lines = slice.map(r =>
    `${pad(r.id, COL_WIDTHS.id)} ${pad(r.ping, COL_WIDTHS.ping)} ${pad(r.guilds, COL_WIDTHS.guilds)} ${pad(r.users, COL_WIDTHS.users)} ${pad(fmtMb(r.memoryMB), COL_WIDTHS.mem)} ${pad(fmtUptime(r.uptime), COL_WIDTHS.up)}`
  );

  return '```text\n' + header + '\n' + lines.join('\n') + '\n```';
}

function buildButtons(page, totalPages, disabled = false) {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('first').setEmoji('⏮️').setStyle(ButtonStyle.Secondary).setDisabled(disabled || page === 0),
    new ButtonBuilder().setCustomId('prev').setEmoji('◀️').setStyle(ButtonStyle.Secondary).setDisabled(disabled || page === 0),
    new ButtonBuilder().setCustomId('refresh').setEmoji('🔄').setStyle(ButtonStyle.Primary).setDisabled(disabled),
    new ButtonBuilder().setCustomId('next').setEmoji('▶️').setStyle(ButtonStyle.Secondary).setDisabled(disabled || page >= totalPages - 1),
    new ButtonBuilder().setCustomId('last').setEmoji('⏭️').setStyle(ButtonStyle.Secondary).setDisabled(disabled || page >= totalPages - 1),
  );
}

export const data = new SlashCommandBuilder()
  .setName('shards')
  .setDescription('Affiche un tableau paginé des shards et leurs stats.')
  .setDMPermission(false);

export async function execute(interaction) {
  await interaction.deferReply({ ephemeral: true });

  let page = 0;
  let snapshot = await fetchShardSnapshot(interaction.client);
  const totalPages = Math.max(1, Math.ceil(snapshot.length / PAGE_SIZE));

  const totals = {
    shards: snapshot.length,
    ping: avg(snapshot, 'ping'),
    guilds: sum(snapshot, 'guilds'),
    users: sum(snapshot, 'users'),
    mem: sum(snapshot, 'memoryMB')
  };

  const embed = new EmbedBuilder()
    .setTitle('📊 Shards — Vue d’ensemble')
    .setColor(0x00aaff)
    .setDescription(
      `**Actifs :** ${totals.shards} | **Ping moyen :** ${totals.ping}ms | ` +
      `**Guilds :** ${totals.guilds} | **Users :** ${totals.users.toLocaleString()} | **RAM :** ${fmtMb(totals.mem)} MB`
    )
    .addFields({
      name: `Page ${page + 1}/${totalPages}`,
      value: renderTablePage(snapshot, page, PAGE_SIZE)
    })
    .setTimestamp();

  const msg = await interaction.editReply({ embeds: [embed], components: [buildButtons(page, totalPages)] });

  // Collector de 60s pour naviguer
  const collector = msg.createMessageComponentCollector({ time: 60_000 });

  collector.on('collect', async (btn) => {
    if (btn.user.id !== interaction.user.id) return btn.reply({ content: 'Commande ouverte par un autre utilisateur.', ephemeral: true });

    if (btn.customId === 'first') page = 0;
    if (btn.customId === 'prev') page = Math.max(0, page - 1);
    if (btn.customId === 'next') page = Math.min(totalPages - 1, page + 1);
    if (btn.customId === 'last') page = totalPages - 1;
    if (btn.customId === 'refresh') {
      // rafraîchir les métriques sans recréer l’embed
      snapshot = await fetchShardSnapshot(interaction.client);
      totals.shards = snapshot.length;
      totals.ping = avg(snapshot, 'ping');
      totals.guilds = sum(snapshot, 'guilds');
      totals.users = sum(snapshot, 'users');
      totals.mem = sum(snapshot, 'memoryMB');
    }

    const updated = EmbedBuilder.from(embed)
      .setDescription(
        `**Actifs :** ${totals.shards} | **Ping moyen :** ${totals.ping}ms | ` +
        `**Guilds :** ${totals.guilds} | **Users :** ${totals.users.toLocaleString()} | **RAM :** ${fmtMb(totals.mem)} MB`
      )
      .spliceFields(0, 1, {
        name: `Page ${page + 1}/${totalPages}`,
        value: renderTablePage(snapshot, page, PAGE_SIZE)
      })
      .setTimestamp(new Date());

    await btn.update({ embeds: [updated], components: [buildButtons(page, totalPages)] });
  });

  collector.on('end', async () => {
    // désactiver les boutons à la fin
    await msg.edit({ components: [buildButtons(page, totalPages, true)] }).catch(() => {});
  });
}
