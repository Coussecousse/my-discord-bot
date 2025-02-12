import discord
from discord import app_commands
from discord.ext import commands

class DatabaseCommands(app_commands.Group):
    """Commands to interact with the database"""

    @app_commands.command(name="create_user", description="Créer un utilisateur")
    async def create_user(self, interaction: discord.Interaction, username: str):
        await interaction.response.send_message(f"Utilisateur {username} créé avec succès !", ephemeral=True)

    @app_commands.command(name="update_user_description", description="Mettre à jour la description d'un utilisateur")
    async def update_user_description(self, interaction: discord.Interaction, username: str, description: str):
        await interaction.response.send_message(f"Description de {username} mise à jour : {description}", ephemeral=True)

    @app_commands.command(name="change_password", description="Changer le mot de passe d'un utilisateur")
    async def change_password(self, interaction: discord.Interaction, username: str, new_password: str):
        await interaction.response.send_message(f"Mot de passe de {username} changé avec succès !", ephemeral=True)

    @app_commands.command(name="add_birthday", description="Ajouter une date d'anniversaire")
    async def add_birthday(self, interaction: discord.Interaction, username: str, birthday: str):
        await interaction.response.send_message(f"Anniversaire de {username} ajouté : {birthday}", ephemeral=True)

# class DatabaseCommands(app_commands.Group):
#     """Commands to interact with the database"""

#     @app_commands.command(name="update_user_description", description="Mettre à jour la description d'un utilisateur")
#     async def update_user_description(self, interaction: discord.Interaction, username: str, password: str, description: str):
#         if username not in USER_DATABASE:
#             await interaction.response.send_message(f"⚠️ L'utilisateur {username} n'existe pas.", ephemeral=True)
#             return

#         # Check if the provided password is correct
#         if USER_DATABASE[username]["password"] != password:
#             await interaction.response.send_message("❌ Mot de passe incorrect.", ephemeral=True)
#             return

#         # Update the description
#         USER_DATABASE[username]["description"] = description
#         await interaction.response.send_message(f"✅ Description de {username} mise à jour : {description}", ephemeral=True)