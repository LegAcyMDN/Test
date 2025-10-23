import { PermissionFlagsBits } from 'discord.js';

export function mustHaveModPerms(member) {
  return member.permissions.has(PermissionFlagsBits.ModerateMembers) ||
         member.permissions.has(PermissionFlagsBits.KickMembers) ||
         member.permissions.has(PermissionFlagsBits.BanMembers) ||
         member.permissions.has(PermissionFlagsBits.Administrator);
}
