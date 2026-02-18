using System.ComponentModel.DataAnnotations;

namespace StravaSharp.OAuth2Client;

public class OAuth2ClientConfiguration
{
    [Required]
    public required string ClientId { get; set; }
    [Required]
    public required string ClientSecret { get; set; }
    [Required]
    public required string RedirectUri { get; set; }
    [Required]
    public required string Scope { get; set; }
    [Required]
    public required string AccessToken { get; set; }
    [Required]
    public required string RefreshToken { get; set; }
    [Required]
    public required DateTime TokenExpiresAt { get; set; }
}
